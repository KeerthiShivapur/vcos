"""Education pack definition (Phase 17.4).

Universities, schools, training centers and research institutes. Modules cover
students, teachers, courses, examinations, research, the academic calendar,
attendance and learning analytics. The AI provides an AI tutor, learning
recommendations, academic analytics and student engagement insights.
"""

INDUSTRY_PACK = {
    "key": "education",
    "name": "Education Pack",
    "icon": "graduation-cap",
    "color": "#8b5cf6",
    "description": "Universities, schools, training centers and research institutes — students, teachers, courses, examinations, attendance, academic calendar, research and learning analytics.",
    "business_types": ["university", "school", "training_center", "research_institute", "college", "academy", "online_education"],
    "countries": ["US", "GB", "IN", "AU", "CA", "DE", "FR", "SG", "NG", "BR"],
    "modules": [
        {"key": "students", "name": "Students", "category": "academic", "description": "Student registry, enrollment, records and transcripts.", "entities": ["student"], "permissions": []},
        {"key": "teachers", "name": "Teachers", "category": "academic", "description": "Faculty profiles, assignments, workloads and development.", "entities": ["teacher"], "permissions": []},
        {"key": "courses", "name": "Courses", "category": "academic", "description": "Course catalog, syllabi, modules and materials.", "entities": ["course"], "permissions": []},
        {"key": "examinations", "name": "Examinations", "category": "academic", "description": "Exam schedules, grading, results and malpractice checks.", "entities": ["examination"], "permissions": []},
        {"key": "attendance", "name": "Attendance", "category": "academic", "description": "Class attendance, tracking and reporting.", "entities": ["attendance"], "permissions": []},
        {"key": "academic-calendar", "name": "Academic Calendar", "category": "operations", "description": "Terms, semesters, holidays and key dates.", "entities": ["academic_term"], "permissions": []},
        {"key": "learning-analytics", "name": "Learning Analytics", "category": "analytics", "description": "Engagement, performance trends and at-risk flags.", "entities": ["learning_metric"], "permissions": []},
        {"key": "campus-communities", "name": "Campus Communities", "category": "operations", "description": "Clubs, societies, events and alumni.", "entities": ["campus_group"], "permissions": []},
        {"key": "academic-research", "name": "Research", "category": "research", "description": "Faculty research projects, publications and funding.", "entities": ["research_project"], "permissions": []},
    ],
    "templates": [
        {"key": "syllabus", "name": "Course Syllabus", "kind": "document", "description": "Standard course syllabus.", "content": {"sections": ["Course info", "Learning outcomes", "Schedule", "Assessment", "Grading policy", "Resources", "Academic integrity"]}},
        {"key": "exam-results", "name": "Examination Results Sheet", "kind": "document", "description": "Results release template.", "content": {"sections": ["Examination", "Course", "Student list", "Marks", "Grade distribution", "Remediation"]}},
        {"key": "lesson-plan", "name": "Lesson Plan", "kind": "document", "description": "Teacher lesson plan.", "content": {"sections": ["Lesson", "Objectives", "Activities", "Materials", "Assessment", "Differentiation"]}},
        {"key": "education-dashboard", "name": "Institution Dashboard", "kind": "dashboard", "description": "Enrollment, performance, attendance and engagement panels.", "content": {"panels": ["Enrollment", "Attendance rate", "Grade distribution", "At-risk students", "Course fill rate", "Teacher load"]}},
        {"key": "education-report", "name": "Term Performance Report", "kind": "report", "description": "End-of-term academic report.", "content": {"metrics": ["enrollment", "attendance_rate", "pass_rate", "engagement_index", "course_fill_rate", "at_risk_students"]}},
    ],
    "workflows": [
        {"key": "admission-flow", "name": "Student Admission", "description": "Application to enrollment.", "steps": [
            {"key": "application", "name": "Application", "assignee_role": "admissions_office"},
            {"key": "review", "name": "Application Review", "assignee_role": "admissions_committee"},
            {"key": "offer", "name": "Offer Letter", "assignee_role": "admissions_office"},
            {"key": "acceptance", "name": "Acceptance & Fees", "assignee_role": "student_services"},
            {"key": "enrollment", "name": "Enrollment & Orientation", "assignee_role": "registrar"},
        ]},
        {"key": "exam-cycle", "name": "Examination Cycle", "description": "Schedule to results release.", "steps": [
            {"key": "scheduling", "name": "Exam Scheduling", "assignee_role": "exams_office"},
            {"key": "paper-preparation", "name": "Paper Preparation", "assignee_role": "subject_lead"},
            {"key": "invigilation", "name": "Invigilation Roster", "assignee_role": "exams_office"},
            {"key": "grading", "name": "Grading", "assignee_role": "teachers"},
            {"key": "review", "name": "Result Review", "assignee_role": "academic_lead"},
            {"key": "release", "name": "Results Release", "assignee_role": "exams_office"},
        ]},
        {"key": "course-approval", "name": "New Course Approval", "description": "Proposal to catalog.", "steps": [
            {"key": "proposal", "name": "Course Proposal", "assignee_role": "faculty"},
            {"key": "department-review", "name": "Department Review", "assignee_role": "department_head"},
            {"key": "accreditation-check", "name": "Accreditation Check", "assignee_role": "quality_office"},
            {"key": "approval", "name": "Academic Council Approval", "assignee_role": "dean"},
            {"key": "publish", "name": "Catalog Publication", "assignee_role": "registrar"},
        ]},
    ],
    "compliance": [
        {"framework": "Accreditation", "region": "global", "rules": [
            {"key": "accreditation-renewal", "name": "Accreditation renewal milestones tracked", "control": "Standards", "severity": "critical", "evidence": ["documents", "calendar"], "cadence_days": 90},
            {"key": "faculty-qualifications", "name": "Faculty qualification records current", "control": "Standards", "severity": "high", "evidence": ["training", "documents"], "cadence_days": 180},
        ]},
        {"framework": "FERPA", "region": "US", "rules": [
            {"key": "ferpa-records", "name": "Student records access controls", "control": "Privacy", "severity": "critical", "evidence": ["audit_log", "security_policy"], "cadence_days": 90},
        ]},
        {"framework": "GDPR / Student Data", "region": "EU", "rules": [
            {"key": "student-data-protection", "name": "Student data protection safeguards", "control": "Data Protection", "severity": "high", "evidence": ["audit_log", "data_map"], "cadence_days": 90},
        ]},
    ],
    "ai": {"models": [
        {"key": "education-assistant", "name": "Academic Operations Assistant", "system_prompt": "You assist academic leaders with enrollment, courses, examinations, attendance, research and student success. Use the institution's student, faculty and course data. Engagement and performance insights always surface at-risk students to staff.", "terminology": ["enrollment", "attendance rate", "pass rate", "grade distribution", "at-risk student", "semester", "credit load", "accreditation"], "knowledge_scope": {"domains": ["academic administration", "student success", "curriculum design", "education compliance"]}, "guardrails": ["Never release individual student results to unauthorized roles", "Frame at-risk flags as advisory signals for staff follow-up"], "skills": {"summarize": "Summarize enrollment, attendance and academic performance.", "tutor": "Provide learning support guidance grounded in course materials.", "assist": "Answer administrative questions from academic records."}},
    ]},
    "kpis": [
        {"key": "enrollment", "name": "Enrollment", "unit": "students", "benchmark": 500},
        {"key": "attendance_rate", "name": "Attendance Rate", "unit": "%", "benchmark": 90},
        {"key": "pass_rate", "name": "Pass Rate", "unit": "%", "benchmark": 85},
        {"key": "engagement_index", "name": "Engagement Index", "unit": "index", "benchmark": 75},
        {"key": "course_fill_rate", "name": "Course Fill Rate", "unit": "%", "benchmark": 85},
        {"key": "at_risk_students", "name": "At-Risk Students", "unit": "count", "benchmark": 5},
    ],
    "navigation": {"label": "Education", "sections": ["Students", "Teachers", "Courses", "Examinations", "Attendance", "Academic Calendar", "Learning Analytics", "Campus Communities", "Research"]},
}
