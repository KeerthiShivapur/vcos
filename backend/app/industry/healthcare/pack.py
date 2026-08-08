"""Healthcare pack definition (Phase 17.2).

Hospitals, clinics, medical colleges and diagnostic labs. Modules cover
patients, appointments, clinical teams, medical knowledge, compliance,
equipment, hospital operations and medical documents. The AI profile assists
with clinical documentation assistance, resource scheduling, knowledge
retrieval and administrative summaries — never diagnostic/treatment decisions
without appropriate safeguards.
"""

INDUSTRY_PACK = {
    "key": "healthcare",
    "name": "Healthcare Pack",
    "icon": "stethoscope",
    "color": "#0ea5e9",
    "description": "Hospitals, clinics, medical colleges and diagnostic labs — patients, appointments, clinical teams, medical equipment, hospital operations, medical knowledge, compliance and documentation.",
    "business_types": ["hospital", "clinic", "diagnostic_lab", "medical_college", "healthcare_startup", "pharmacy", "telehealth", "rehabilitation"],
    "countries": ["US", "GB", "IN", "DE", "FR", "CA", "AU", "SG", "AE", "BR"],
    "modules": [
        {"key": "patients", "name": "Patients", "category": "care", "description": "Patient registry, medical records, vitals and care plans.", "entities": ["patient"], "permissions": []},
        {"key": "appointments", "name": "Appointments", "category": "care", "description": "Scheduling, calendar integration, reminders and no-show tracking.", "entities": ["appointment"], "permissions": []},
        {"key": "clinical-teams", "name": "Clinical Teams", "category": "operations", "description": "Doctors, nurses, departments, shifts and on-call coverage.", "entities": ["clinical_team"], "permissions": []},
        {"key": "medical-knowledge", "name": "Medical Knowledge", "category": "knowledge", "description": "Clinical protocols, guidelines, formularies and best practices.", "entities": ["medical_knowledge"], "permissions": []},
        {"key": "healthcare-compliance", "name": "Compliance", "category": "compliance", "description": "HIPAA, GDPR, licensing, training and audit readiness.", "entities": ["compliance_control"], "permissions": []},
        {"key": "medical-equipment", "name": "Medical Equipment", "category": "operations", "description": "Equipment registry, calibration, maintenance and utilization.", "entities": ["equipment"], "permissions": []},
        {"key": "hospital-operations", "name": "Hospital Operations", "category": "operations", "description": "Beds, wards, occupancy, inventory and operational readiness.", "entities": ["ward", "bed"], "permissions": []},
        {"key": "medical-documents", "name": "Medical Documents", "category": "knowledge", "description": "Consent forms, discharge summaries, referral letters and records.", "entities": ["medical_document"], "permissions": []},
    ],
    "templates": [
        {"key": "patient-consent", "name": "Patient Consent Form", "kind": "document", "description": "Standard informed consent form.", "content": {"sections": ["Patient details", "Procedure", "Risks", "Benefits", "Alternatives", "Acknowledgement", "Signatures"]}},
        {"key": "discharge-summary", "name": "Discharge Summary", "kind": "document", "description": "Structured discharge summary template.", "content": {"sections": ["Admission summary", "Diagnosis", "Treatment", "Medications", "Follow-up plan", "Instructions"]}},
        {"key": "referral-letter", "name": "Referral Letter", "kind": "document", "description": "Specialist referral letter.", "content": {"sections": ["Patient", "Reason for referral", "History", "Findings", "Request", "Attachments"]}},
        {"key": "hospital-dashboard", "name": "Hospital Operations Dashboard", "kind": "dashboard", "description": "Occupancy, appointments, equipment and compliance panels.", "content": {"panels": ["Bed occupancy", "Appointments today", "No-show rate", "Equipment uptime", "Compliance posture", "Ward load"]}},
        {"key": "hospital-report", "name": "Daily Operations Report", "kind": "report", "description": "Daily hospital operations summary.", "content": {"metrics": ["bed_occupancy_rate", "appointment_fill_rate", "no_show_rate", "avg_length_of_stay", "equipment_uptime", "compliance_score"]}},
    ],
    "workflows": [
        {"key": "patient-admission", "name": "Patient Admission", "description": "Registration to discharge — the standard hospital flow.", "steps": [
            {"key": "patient-registration", "name": "Patient Registration", "assignee_role": "front_desk"},
            {"key": "doctor-assignment", "name": "Doctor Assignment", "assignee_role": "clinical_coordinator"},
            {"key": "diagnosis", "name": "Diagnosis", "assignee_role": "doctor"},
            {"key": "treatment", "name": "Treatment Plan", "assignee_role": "doctor"},
            {"key": "discharge", "name": "Discharge", "assignee_role": "care_coordinator"},
            {"key": "knowledge-update", "name": "Knowledge Update", "assignee_role": "clinical_lead"},
        ]},
        {"key": "appointment-booking", "name": "Appointment Booking", "description": "Request to confirmed appointment.", "steps": [
            {"key": "request", "name": "Appointment Request", "assignee_role": "front_desk"},
            {"key": "slot-matching", "name": "Slot Matching", "assignee_role": "front_desk"},
            {"key": "confirmation", "name": "Confirmation", "assignee_role": "front_desk"},
            {"key": "reminder", "name": "Reminder", "assignee_role": "automation"},
            {"key": "visit", "name": "Patient Visit", "assignee_role": "clinical_staff"},
        ]},
        {"key": "equipment-maintenance", "name": "Equipment Maintenance", "description": "Fault report to recalibration.", "steps": [
            {"key": "report", "name": "Fault Report", "assignee_role": "clinical_staff"},
            {"key": "triage", "name": "Maintenance Triage", "assignee_role": "biomedical_engineer"},
            {"key": "repair", "name": "Repair", "assignee_role": "biomedical_engineer"},
            {"key": "calibration", "name": "Calibration", "assignee_role": "biomedical_engineer"},
            {"key": "release", "name": "Release to Service", "assignee_role": "clinical_lead"},
        ]},
    ],
    "compliance": [
        {"framework": "HIPAA", "region": "US", "rules": [
            {"key": "hipaa-privacy", "name": "Protected health information access controls", "control": "Privacy Rule", "severity": "critical", "evidence": ["audit_log", "security_policy"], "cadence_days": 90},
            {"key": "hipaa-breach", "name": "Breach notification process in place", "control": "Breach Notification", "severity": "critical", "evidence": ["incident_report"], "cadence_days": 30},
            {"key": "hipaa-training", "name": "Workforce privacy training completed", "control": "Security Rule", "severity": "high", "evidence": ["training"], "cadence_days": 180},
        ]},
        {"framework": "GDPR", "region": "EU", "rules": [
            {"key": "gdpr-health-data", "name": "Special category data safeguards", "control": "Art. 9", "severity": "critical", "evidence": ["audit_log", "data_map"], "cadence_days": 90},
        ]},
        {"framework": "Hospital Licensing", "region": "global", "rules": [
            {"key": "licensing-renewal", "name": "Facility license renewals tracked", "control": "Licensing", "severity": "high", "evidence": ["licenses", "calendar"], "cadence_days": 90},
        ]},
    ],
    "ai": {"models": [
        {"key": "healthcare-assistant", "name": "Healthcare Operations Assistant", "system_prompt": "You assist hospital and clinic administrators with operations, scheduling, knowledge retrieval and administrative summaries. Use the organization's patients, appointments, clinical teams, equipment and compliance data. You never provide diagnostic or treatment decisions without explicit human clinical review.", "terminology": ["bed occupancy", "no-show rate", "triage", "discharge summary", "informed consent", "clinical protocol", "ward", "on-call"], "knowledge_scope": {"domains": ["hospital operations", "patient scheduling", "clinical documentation", "healthcare compliance"], "sensitive": ["PHI"]}, "guardrails": ["Never make diagnostic or treatment decisions", "Treat all patient data as protected health information", "Never share patient details outside the organization"], "skills": {"summarize": "Summarize today's hospital operations across wards, appointments and equipment.", "schedule": "Recommend appointment slot allocation from utilization patterns.", "retrieve": "Retrieve relevant clinical protocols and knowledge.", "assist": "Answer administrative questions using hospital records."}},
    ]},
    "kpis": [
        {"key": "bed_occupancy_rate", "name": "Bed Occupancy Rate", "unit": "%", "benchmark": 80},
        {"key": "appointment_fill_rate", "name": "Appointment Fill Rate", "unit": "%", "benchmark": 85},
        {"key": "no_show_rate", "name": "No-Show Rate", "unit": "%", "benchmark": 10},
        {"key": "avg_length_of_stay", "name": "Average Length of Stay", "unit": "days", "benchmark": 4},
        {"key": "equipment_uptime", "name": "Equipment Uptime", "unit": "%", "benchmark": 95},
        {"key": "compliance_score", "name": "Compliance Score", "unit": "%", "benchmark": 90},
    ],
    "navigation": {"label": "Healthcare", "sections": ["Patients", "Appointments", "Clinical Teams", "Medical Knowledge", "Compliance", "Medical Equipment", "Hospital Operations", "Medical Documents"]},
}
