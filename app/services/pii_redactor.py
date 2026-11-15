"""PII Redaction Service.

Detects and redacts personal identifiers (names, phones, SSNs, emails,
addresses, and dates of birth) before text is transmitted to external LLM services.
"""

import re
from typing import Dict, NamedTuple


class RedactionResult(NamedTuple):
    """Container holding redacted text and count of masked entities."""

    redacted_text: str
    redactions_count: int
    categories: Dict[str, int]


# Regex patterns for common personal identifiable information
EMAIL_REGEX = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b",
    re.IGNORECASE,
)

PHONE_REGEX = re.compile(
    r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
)

SSN_REGEX = re.compile(
    r"\b\d{3}-\d{2}-\d{4}\b"
)

DOB_REGEX = re.compile(
    r"\b(?:DOB|Date of Birth|Birthdate):\s*(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\w+\s+\d{1,2},\s*\d{4})\b",
    re.IGNORECASE,
)

PATIENT_NAME_REGEX = re.compile(
    r"\b(?:Patient|Elder|Name|Resident):\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b",
    re.IGNORECASE,
)

ADDRESS_REGEX = re.compile(
    r"\b\d{1,5}\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct)\b",
    re.IGNORECASE,
)


def redact_emails(text: str) -> tuple[str, int]:
    """Redact email addresses from text."""
    matches = EMAIL_REGEX.findall(text)
    sanitized = EMAIL_REGEX.sub("[REDACTED_EMAIL]", text)
    return sanitized, len(matches)


def redact_phones(text: str) -> tuple[str, int]:
    """Redact phone numbers from text."""
    matches = PHONE_REGEX.findall(text)
    sanitized = PHONE_REGEX.sub("[REDACTED_PHONE]", text)
    return sanitized, len(matches)


def redact_ssns(text: str) -> tuple[str, int]:
    """Redact Social Security Numbers from text."""
    matches = SSN_REGEX.findall(text)
    sanitized = SSN_REGEX.sub("[REDACTED_ID]", text)
    return sanitized, len(matches)


def redact_dobs(text: str) -> tuple[str, int]:
    """Redact dates of birth from text."""
    matches = DOB_REGEX.findall(text)
    sanitized = DOB_REGEX.sub("DOB: [REDACTED_DOB]", text)
    return sanitized, len(matches)


def redact_names(text: str) -> tuple[str, int]:
    """Redact explicit patient/resident names from text."""
    matches = PATIENT_NAME_REGEX.findall(text)
    sanitized = PATIENT_NAME_REGEX.sub("Patient: [REDACTED_NAME]", text)
    return sanitized, len(matches)


def redact_addresses(text: str) -> tuple[str, int]:
    """Redact street addresses from text."""
    matches = ADDRESS_REGEX.findall(text)
    sanitized = ADDRESS_REGEX.sub("[REDACTED_ADDRESS]", text)
    return sanitized, len(matches)


def redact_pii(text: str) -> RedactionResult:
    """Execute all PII redaction passes on input text before LLM dispatch.

    Args:
        text: Raw text containing potential personal identifiers.

    Returns:
        RedactionResult containing sanitized text and count metrics.
    """
    categories: Dict[str, int] = {}
    current = text

    current, count = redact_emails(current)
    if count:
        categories["emails"] = count

    current, count = redact_phones(current)
    if count:
        categories["phones"] = count

    current, count = redact_ssns(current)
    if count:
        categories["ssns"] = count

    current, count = redact_dobs(current)
    if count:
        categories["dobs"] = count

    current, count = redact_names(current)
    if count:
        categories["names"] = count

    current, count = redact_addresses(current)
    if count:
        categories["addresses"] = count

    total_redacted = sum(categories.values())
    return RedactionResult(
        redacted_text=current,
        redactions_count=total_redacted,
        categories=categories,
    )
