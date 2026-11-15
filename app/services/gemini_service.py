"""Gemini AI assistant service for parsing prescription notes and schedules.

Enforces strict PII redaction prior to LLM interaction and adheres to the
core policy: AI only suggests drafts (PENDING_CONFIRMATION); humans must confirm.
"""

from datetime import datetime, timezone
import json
import re
import uuid
from typing import Any, Dict, List
from app.core.config import settings
from app.core.database import db
from app.models.ai_draft import AIDraft, DraftStatus, DraftType
from app.services.pii_redactor import redact_pii


SYSTEM_EXTRACTION_PROMPT = """You are CareCircle's clinical assistant.
Your job is to read sanitized medical notes and suggest structured drafts for:
1. Medications (name, dosage, instructions, schedule_times, frequency, pill_color)
2. Appointments (title, doctor_name, location, scheduled_time, notes, transport_needed)

Return ONLY valid JSON matching this schema:
{
  "medications": [
    {
      "name": "string",
      "dosage": "string",
      "instructions": "string",
      "schedule_times": ["08:00"],
      "frequency": "Daily",
      "pill_color": "#3B82F6",
      "remaining_refills": 30,
      "refill_threshold": 7,
      "reasoning": "string explanation"
    }
  ],
  "appointments": [
    {
      "title": "string",
      "doctor_name": "string",
      "location": "string",
      "scheduled_time": "string (YYYY-MM-DD HH:MM or relative)",
      "notes": "string",
      "transport_needed": false,
      "reasoning": "string explanation"
    }
  ]
}
"""


def _fallback_heuristic_parser(sanitized_text: str) -> Dict[str, List[Dict[str, Any]]]:
    """Pragmatic fallback extractor when offline or without Gemini API key.

    Parses common prescription patterns like 'Metformin 500mg twice daily with meals'
    or 'Cardiologist appointment on Friday 10am with Dr. Smith'.
    """
    medications: List[Dict[str, Any]] = []
    appointments: List[Dict[str, Any]] = []

    # Heuristic medication pattern: e.g. "Lisinopril 10mg once daily in morning"
    med_pattern = re.compile(
        r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(\d+\s*(?:mg|mcg|ml|tablets?|capsules?))\b(?:\s+([^\n.]+))?",
        re.IGNORECASE,
    )
    for match in med_pattern.finditer(sanitized_text):
        name = match.group(1).strip()
        dosage = match.group(2).strip()
        extra = match.group(3).strip() if match.group(3) else "Take as directed"

        # Skip common non-medication words
        if name.lower() in ["doctor", "hospital", "clinic", "patient", "appointment"]:
            continue

        schedule_times = ["08:00"]
        if "twice" in extra.lower() or "bid" in extra.lower():
            schedule_times = ["08:00", "20:00"]
        elif "three" in extra.lower() or "tid" in extra.lower():
            schedule_times = ["08:00", "14:00", "20:00"]
        elif "night" in extra.lower() or "bedtime" in extra.lower():
            schedule_times = ["21:00"]

        medications.append({
            "name": name,
            "dosage": dosage,
            "instructions": extra[:150],
            "schedule_times": schedule_times,
            "frequency": "Daily",
            "pill_color": "#10B981" if "mg" in dosage else "#3B82F6",
            "remaining_refills": 30,
            "refill_threshold": 7,
            "reasoning": f"Extracted medication dosage '{dosage}' with schedule {schedule_times}",
        })

    # Heuristic appointment pattern: e.g. "appointment with Dr. Adams at City Clinic on Monday 10:00 AM"
    appt_pattern = re.compile(
        r"(?:appointment|visit|consultation)\s+(?:with\s+)?(?:Dr\.\s*([A-Za-z]+))?(?:\s+at\s+([^,.\n]+))?(?:\s+on\s+([^,.\n]+))?",
        re.IGNORECASE,
    )
    for match in appt_pattern.finditer(sanitized_text):
        doc = match.group(1) or "Dr. Specialist"
        loc = match.group(2) or "Medical Center"
        time_hint = match.group(3) or "Upcoming"
        appointments.append({
            "title": f"Follow-up with Dr. {doc}",
            "doctor_name": f"Dr. {doc}",
            "location": loc.strip(),
            "scheduled_time": time_hint.strip(),
            "notes": "Extracted from medical notes",
            "transport_needed": "transport" in sanitized_text.lower(),
            "reasoning": f"Identified appointment with Dr. {doc} at {loc}",
        })

    return {"medications": medications, "appointments": appointments}


def _call_gemini_api(sanitized_text: str) -> Dict[str, List[Dict[str, Any]]]:
    """Call Google GenAI SDK if API key is configured, else fallback."""
    if not settings.gemini_api_key or settings.gemini_api_key == "mock":
        return _fallback_heuristic_parser(sanitized_text)

    try:
        from google import genai  # type: ignore

        client = genai.Client(api_key=settings.gemini_api_key)
        prompt = f"{SYSTEM_EXTRACTION_PROMPT}\n\nSanitized Clinical Notes:\n{sanitized_text}"
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
        )
        raw_output = response.text or "{}"
        clean_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_output.strip())
        parsed = json.loads(clean_json)
        return {
            "medications": parsed.get("medications", []),
            "appointments": parsed.get("appointments", []),
        }
    except Exception:
        # Gracefully fallback if network or API quota error occurs
        return _fallback_heuristic_parser(sanitized_text)


def parse_and_create_drafts(raw_text: str, elder_id: str) -> List[AIDraft]:
    """Redact PII and parse text into unconfirmed AI drafts for human review.

    Strict AI rule: All generated items have status PENDING_CONFIRMATION.
    They are NEVER directly saved as active medications or appointments.

    Args:
        raw_text: Clinical notes or caregiver message.
        elder_id: Target elder ID.

    Returns:
        List of created AIDraft entities waiting for confirmation.
    """
    # 1. Mandatory PII redaction pass
    redaction = redact_pii(raw_text)
    sanitized = redaction.redacted_text

    # 2. Extract structured drafts
    extracted = _call_gemini_api(sanitized)

    created_drafts: List[AIDraft] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    # 3. Create medication drafts
    for med in extracted.get("medications", []):
        draft_id = f"draft_med_{uuid.uuid4().hex[:8]}"
        draft = AIDraft(
            id=draft_id,
            elder_id=elder_id,
            draft_type=DraftType.MEDICATION,
            status=DraftStatus.PENDING_CONFIRMATION,
            source_snippet=sanitized[:200],
            proposed_data=med,
            reasoning=med.get("reasoning", "Suggested medication from prescription text"),
            created_at=now_iso,
        )
        db.set("ai_drafts", draft_id, draft.model_dump())
        created_drafts.append(draft)

    # 4. Create appointment drafts
    for appt in extracted.get("appointments", []):
        draft_id = f"draft_appt_{uuid.uuid4().hex[:8]}"
        draft = AIDraft(
            id=draft_id,
            elder_id=elder_id,
            draft_type=DraftType.APPOINTMENT,
            status=DraftStatus.PENDING_CONFIRMATION,
            source_snippet=sanitized[:200],
            proposed_data=appt,
            reasoning=appt.get("reasoning", "Suggested appointment from notes"),
            created_at=now_iso,
        )
        db.set("ai_drafts", draft_id, draft.model_dump())
        created_drafts.append(draft)

    return created_drafts
