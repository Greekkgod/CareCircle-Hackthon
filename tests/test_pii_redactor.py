"""Tests for PII redaction service before LLM dispatch."""

from app.services.pii_redactor import (
    redact_addresses,
    redact_dobs,
    redact_emails,
    redact_names,
    redact_phones,
    redact_pii,
    redact_ssns,
)


def test_redact_emails():
    """Verify email addresses are properly masked."""
    text = "Contact dr.smith@hospital.org or nurse.mary@clinic.com for questions."
    redacted, count = redact_emails(text)
    assert count == 2
    assert "dr.smith@hospital.org" not in redacted
    assert "nurse.mary@clinic.com" not in redacted
    assert "[REDACTED_EMAIL]" in redacted


def test_redact_phones():
    """Verify phone numbers in various formats are properly masked."""
    text = "Call (555) 123-4567 or +1-800-555-0199 or 555-888-9999 immediately."
    redacted, count = redact_phones(text)
    assert count >= 2
    assert "[REDACTED_PHONE]" in redacted
    assert "(555) 123-4567" not in redacted


def test_redact_ssn():
    """Verify SSNs are masked."""
    text = "Patient SSN is 123-45-6789."
    redacted, count = redact_ssns(text)
    assert count == 1
    assert "123-45-6789" not in redacted
    assert "[REDACTED_ID]" in redacted


def test_redact_dob():
    """Verify date of birth lines are masked."""
    text = "Patient file. DOB: 05/14/1942. Follow up next week."
    redacted, count = redact_dobs(text)
    assert count == 1
    assert "05/14/1942" not in redacted
    assert "[REDACTED_DOB]" in redacted


def test_redact_patient_name():
    """Verify patient names are masked."""
    text = "Discharge Summary. Patient: Rose Dawson. Condition stable."
    redacted, count = redact_names(text)
    assert count == 1
    assert "Rose Dawson" not in redacted
    assert "[REDACTED_NAME]" in redacted


def test_redact_addresses():
    """Verify street addresses are masked."""
    text = "Send medication to 742 Evergreen Terrace or 100 Main Street."
    redacted, count = redact_addresses(text)
    assert count >= 1
    assert "[REDACTED_ADDRESS]" in redacted


def test_combined_pii_redaction_pipeline():
    """Verify end-to-end PII redaction pipeline masks all identifiers."""
    raw = (
        "Patient: Johnathan Miller, DOB: 12/04/1938. Phone: 555-321-7654. "
        "Email: jmiller38@example.net, SSN: 987-65-4321. "
        "Address: 450 Maple Avenue. "
        "Prescription: Lisinopril 20mg once daily in morning."
    )
    res = redact_pii(raw)

    assert res.redactions_count >= 5
    assert "Johnathan Miller" not in res.redacted_text
    assert "jmiller38@example.net" not in res.redacted_text
    assert "987-65-4321" not in res.redacted_text
    assert "555-321-7654" not in res.redacted_text
    # Clinical prescription details MUST remain intact
    assert "Lisinopril 20mg once daily in morning" in res.redacted_text
