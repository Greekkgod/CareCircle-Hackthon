# CareCircle 🌸
> **Accessible Elderly Care & Medication Management Platform**  
> *Built for hackathons with Python 3.12, FastAPI, Google Cloud Firestore, Gemini API, and Vanilla HTML/CSS/JS PWA.*

[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![Firestore](https://img.shields.io/badge/Google%20Cloud-Firestore-orange.svg)](https://cloud.google.com/firestore)
[![Gemini API](https://img.shields.io/badge/Google-Gemini%20API-4285F4.svg)](https://ai.google.dev/)
[![WCAG AAA](https://img.shields.io/badge/Accessibility-WCAG%20AAA-green.svg)](https://www.w3.org/WAI/standards-guidelines/wcag/)
[![Tests](https://img.shields.io/badge/pytest-24%2F24%20passing-brightgreen.svg)]()

---

## 🌟 Overview
**CareCircle** bridges the gap between elderly seniors, professional caregivers, and concerned families. It turns complex prescription notes and discharge paperwork into actionable, stress-free care routines with zero confusion.

### The Problem
- **Medication errors** are among the leading causes of avoidable hospital readmissions in seniors.
- Standard medical apps are cluttered, text-heavy, difficult to read for impaired vision, and frustrating for arthritic hands.
- Family members suffer from constant anxiety about whether medications were taken on time.

### The Solution: CareCircle
1. **Elder View**: Massive high-contrast buttons, 22px base typography, 56px+ touch targets, instant voice readout of the day's schedule via speech synthesis, one-tap "I Took My Pill", and an instant Emergency SOS button.
2. **Caretaker Clinical Console**: AI prescription scanner with automatic PII redaction and strict **human-in-the-loop confirmation**, schedule manager, and refill alert triggers.
3. **Family Reassurance Feed**: Real-time adherence scores, latest mood check-in, recent medication activity timeline, and safety status indicators.

---

## 🛡️ Security & Privacy Architecture

- **Bcrypt Passcode Hashing**: All senior PINs and caregiver passcodes are salted and hashed with `bcrypt`.
- **Brute-Force Rate Limiting**: Consecutive failed passcode attempts are tracked; accounts/IPs are automatically locked after 5 attempts with HTTP 429 and `Retry-After` enforcement.
- **Role-Based Access Control (RBAC)**: Strict role separation (`elder`, `caretaker`, `family`) verified on every API endpoint via signed JWT tokens.
- **Strict PII Redaction Before AI**: All text submitted to the AI assistant is pre-processed through a clinical redaction engine that masks names, phone numbers, Social Security Numbers, dates of birth, and physical addresses before reaching any LLM.
- **AI Human-in-the-Loop Rule**: AI models *only draft proposals* (`PENDING_CONFIRMATION`). No active medication or appointment is created until a human explicitly reviews, edits, and confirms it.
- **Security Headers Middleware**: Enforces `Content-Security-Policy`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Strict-Transport-Security`, `Referrer-Policy`, and `Permissions-Policy`.

---

## ♿ Accessibility First (WCAG AAA)

- **22px Base Text**: Large, high-legibility system fonts designed for aging eyesight.
- **56px+ Touch Targets**: All interactive elements (buttons, inputs, cards) exceed 56px in height and width to prevent missed taps.
- **4.5:1+ Contrast Ratio**: Deep slate backgrounds (`#0F172A`) paired with bright, high-contrast text (`#FFFFFF`, `#93C5FD`, `#34D399`).
- **Screen Reader Friendly**: Full semantic HTML (`<main>`, `<nav>`, `<article>`, `<section>`, `<button>`), ARIA live regions (`aria-live="polite"`), and `<label>` bindings on every control.
- **Keyboard Navigation**: `:focus-visible` high-contrast focus rings and a visible "Skip to main content" link.
- **Reduced Motion Support**: Fully respects `@media (prefers-reduced-motion: reduce)`.
- **Speech Synthesis Readout**: Integrated Web Speech API reads daily schedules aloud with one touch.

---

## 📁 Repository Structure
```
PromptWars-x-Catalyst/
├── app/
│   ├── core/
│   │   ├── config.py         # Pydantic Settings & environment variables
│   │   ├── database.py       # Firestore client & thread-safe mock store
│   │   ├── middleware.py     # HTTP security headers middleware
│   │   └── security.py       # Bcrypt hashing, JWT, and rate limiter
│   ├── models/
│   │   ├── ai_draft.py       # AI draft & confirmation schemas
│   │   ├── appointment.py    # Medical appointment models
│   │   ├── auth.py           # User, passcode, and role models
│   │   ├── checkin.py        # Mood check-in and emergency SOS models
│   │   └── medication.py     # Medication schedules, logs, and adherence
│   ├── routes/
│   │   ├── ai_assistant.py   # AI prescription scanner & draft approval
│   │   ├── appointments.py   # Appointment scheduling routes
│   │   ├── auth.py           # Passcode login & rate-limit status
│   │   ├── checkins.py       # Wellness check-ins & emergency SOS
│   │   └── medications.py    # Medications, dose logs, and adherence
│   ├── services/
│   │   ├── appointment_service.py # Appointment business logic
│   │   ├── auth_service.py        # Auth & demo user seeding
│   │   ├── checkin_service.py     # Check-in & emergency dispatch logic
│   │   ├── draft_service.py       # Human-in-the-loop draft confirmation
│   │   ├── gemini_service.py      # Gemini API client & heuristic fallback
│   │   ├── medication_service.py   # Medication CRUD & adherence engine
│   │   └── pii_redactor.py        # Regular expression PII masking engine
│   └── main.py               # FastAPI application entry point
├── static/
│   ├── css/
│   │   └── app.css           # Accessible WCAG AAA stylesheet
│   ├── icons/
│   │   └── icon.svg          # CareCircle vector app icon
│   ├── js/
│   │   └── app.js            # Vanilla PWA frontend logic & speech synth
│   ├── index.html            # Semantic Single Page Application
│   ├── manifest.webmanifest  # PWA manifest
│   └── sw.js                 # Offline service worker
├── tests/
│   ├── conftest.py           # Test fixtures & mock DB isolation
│   ├── test_ai_draft_rules.py         # AI human confirmation rule tests
│   ├── test_medications_adherence.py  # Dose logging & refill tests
│   ├── test_pii_redactor.py           # PII masking verification
│   ├── test_pwa_and_accessibility.py  # WCAG & PWA validation
│   ├── test_roles_permissions.py      # RBAC permission tests
│   └── test_security_and_passcodes.py # Bcrypt, headers, rate limits
├── .env.example              # Sample environment variables
├── .gitignore                # Git ignore patterns (<10MB repo guarantee)
├── pytest.ini                # Pytest configuration
├── requirements.txt          # Production and test dependencies
└── README.md                 # Complete documentation
```

---

## 🚀 Quickstart & Installation

### Prerequisites
- Python 3.12+
- `uv` (recommended) or standard `pip`

### 1. Clone & Set Up Environment
```bash
git clone https://github.com/Greekkgod/PromptWars-x-Catalyst.git
cd PromptWars-x-Catalyst

# Create virtual environment with Python 3.12
uv venv --python 3.12 .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
uv pip install -r requirements.txt
```

### 2. Configure Environment Variables
```bash
cp .env.example .env
```
*(Default settings run seamlessly with in-memory Firestore and heuristic AI parsing without requiring cloud credentials).*

### 3. Run the Platform
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
Open your browser at **http://localhost:8000** to explore the PWA interface, or **http://localhost:8000/docs** for the OpenAPI specification.

---

## 🔑 Demo Credentials

| Role | Username / Identifier | Passcode | Description |
| :--- | :--- | :--- | :--- |
| **👵 Elder** | `elder_1` | `1234` | Large text, 1-tap pill logging, SOS, speech readout |
| **🩺 Caretaker** | `caretaker_1` | `care2026` | AI scanner, draft confirmation, refill tracker |
| **❤️ Family** | `family_1` | `fam1234` | Reassurance metrics, adherence rate, love notes |

---

## 🧪 Testing

Run the comprehensive pytest suite:
```bash
pytest -v
```

Output:
```
============================= test session starts =============================
collected 24 items

tests/test_ai_draft_rules.py::test_ai_draft_requires_human_confirmation PASSED
tests/test_medications_adherence.py::test_log_dose_decrements_refills PASSED
tests/test_medications_adherence.py::test_adherence_calculation PASSED
tests/test_medications_adherence.py::test_daily_mood_checkin PASSED
tests/test_medications_adherence.py::test_emergency_sos_trigger_and_resolve PASSED
tests/test_pii_redactor.py::test_redact_emails PASSED
tests/test_pii_redactor.py::test_redact_phones PASSED
tests/test_pii_redactor.py::test_redact_ssn PASSED
tests/test_pii_redactor.py::test_redact_dob PASSED
tests/test_pii_redactor.py::test_redact_patient_name PASSED
tests/test_pii_redactor.py::test_redact_addresses PASSED
tests/test_pii_redactor.py::test_combined_pii_redaction_pipeline PASSED
tests/test_pwa_and_accessibility.py::test_pwa_manifest_endpoint PASSED
tests/test_pwa_and_accessibility.py::test_pwa_service_worker_endpoint PASSED
tests/test_pwa_and_accessibility.py::test_accessibility_html_semantics_and_aria PASSED
tests/test_pwa_and_accessibility.py::test_accessibility_css_tokens PASSED
tests/test_roles_permissions.py::test_elder_permissions PASSED
tests/test_roles_permissions.py::test_caretaker_permissions PASSED
tests/test_roles_permissions.py::test_family_permissions PASSED
tests/test_security_and_passcodes.py::test_passcode_bcrypt_hashing PASSED
tests/test_security_and_passcodes.py::test_rate_limiter_lockout_mechanism PASSED
tests/test_security_and_passcodes.py::test_auth_login_rate_limiting_endpoint PASSED
tests/test_security_and_passcodes.py::test_security_headers_present PASSED
tests/test_security_and_passcodes.py::test_unauthenticated_request_rejected PASSED

============================= 24 passed in 18.86s =============================
```

---

## 📜 License
MIT License. Created for the Hackathon.
