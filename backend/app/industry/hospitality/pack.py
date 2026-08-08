"""Hospitality pack definition (Phase 17.10).

Hotels, restaurants, travel and resorts. Modules cover reservations, guests,
housekeeping, maintenance, events, restaurants and training. The AI does
scheduling, service recommendations and operational analytics.
"""

INDUSTRY_PACK = {
    "key": "hospitality",
    "name": "Hospitality Pack",
    "icon": "concierge-bell",
    "color": "#a855f7",
    "description": "Hotels, restaurants, travel and resorts — reservations, guests, housekeeping, maintenance, events, restaurants and training.",
    "business_types": ["hotel", "resort", "restaurant", "travel_company", "event_venue", "hostel", "cafe_chain"],
    "countries": ["US", "GB", "AE", "FR", "TH", "ES", "IN", "SG", "MX", "JP"],
    "modules": [
        {"key": "reservations", "name": "Reservations", "category": "operations", "description": "Booking engine, rates, overbooking and no-shows.", "entities": ["reservation"], "permissions": []},
        {"key": "guests", "name": "Guests", "category": "crm", "description": "Guest profiles, preferences, loyalty and history.", "entities": ["guest"], "permissions": []},
        {"key": "housekeeping", "name": "Housekeeping", "category": "operations", "description": "Room status, cleaning schedules and inspections.", "entities": ["room"], "permissions": []},
        {"key": "maintenance", "name": "Maintenance", "category": "operations", "description": "Facility maintenance requests and work orders.", "entities": ["maintenance_job"], "permissions": []},
        {"key": "events", "name": "Events", "category": "operations", "description": "Banquets, conferences and event logistics.", "entities": ["event"], "permissions": []},
        {"key": "restaurants", "name": "Restaurants", "category": "operations", "description": "F&B outlets, menus, covers and inventory.", "entities": ["outlet"], "permissions": []},
        {"key": "hospitality-training", "name": "Training", "category": "people", "description": "Service standards, certifications and audits.", "entities": ["training"], "permissions": []},
    ],
    "templates": [
        {"key": "guest-preference", "name": "Guest Preference Card", "kind": "document", "description": "Guest preferences and notes.", "content": {"sections": ["Guest", "Preferences", "Allergies", "Special occasions", "Past issues", "VIP notes"]}},
        {"key": "housekeeping-checklist", "name": "Room Inspection Checklist", "kind": "document", "description": "Room readiness checklist.", "content": {"sections": ["Room", "Cleanliness", "Amenities", "Maintenance issues", "Minibar", "Reinspect"]}},
        {"key": "event-brief", "name": "Event Brief", "kind": "document", "description": "Event requirements brief.", "content": {"sections": ["Event", "Guest count", "Layout", "F&B", "AV", "Timeline", "Contact"]}},
        {"key": "hospitality-dashboard", "name": "Property Dashboard", "kind": "dashboard", "description": "Occupancy, revenue, housekeeping and events panels.", "content": {"panels": ["Occupancy rate", "ADR", "RevPAR", "Housekeeping backlog", "Guest satisfaction", "Event pipeline"]}},
        {"key": "hospitality-report", "name": "Daily Revenue Report", "kind": "report", "description": "Daily property revenue report.", "content": {"metrics": ["occupancy_rate", "adr", "revpar", "housekeeping_backlog", "guest_satisfaction", "no_show_rate"]}},
    ],
    "workflows": [
        {"key": "guest-stay-lifecycle", "name": "Guest Stay Lifecycle", "description": "Booking to follow-up.", "steps": [
            {"key": "reservation", "name": "Reservation", "assignee_role": "front_desk"},
            {"key": "pre-arrival", "name": "Pre-Arrival Prep", "assignee_role": "guest_relations"},
            {"key": "check-in", "name": "Check-In", "assignee_role": "front_desk"},
            {"key": "stay", "name": "Stay Services", "assignee_role": "concierge"},
            {"key": "check-out", "name": "Check-Out", "assignee_role": "front_desk"},
            {"key": "follow-up", "name": "Follow-Up", "assignee_role": "guest_relations"},
        ]},
        {"key": "event-booking", "name": "Event Booking", "description": "Inquiry to confirmation.", "steps": [
            {"key": "inquiry", "name": "Event Inquiry", "assignee_role": "events_sales"},
            {"key": "proposal", "name": "Proposal & Quote", "assignee_role": "events_sales"},
            {"key": "contract", "name": "Contract", "assignee_role": "events_sales"},
            {"key": "preparation", "name": "Event Preparation", "assignee_role": "banquet_manager"},
            {"key": "execution", "name": "Event Execution", "assignee_role": "banquet_manager"},
            {"key": "post-event", "name": "Post-Event Review", "assignee_role": "events_sales"},
        ]},
    ],
    "compliance": [
        {"framework": "Health & Food Safety", "region": "global", "rules": [
            {"key": "food-safety-audit", "name": "Kitchen hygiene audits current", "control": "Food Safety", "severity": "critical", "evidence": ["audit_log", "inspection"], "cadence_days": 30},
            {"key": "allergen-labels", "name": "Allergen labeling compliance", "control": "Food Safety", "severity": "high", "evidence": ["menu_audit"], "cadence_days": 90},
        ]},
        {"framework": "Guest Data Protection", "region": "global", "rules": [
            {"key": "guest-data-controls", "name": "Guest data access controls", "control": "Privacy", "severity": "high", "evidence": ["audit_log", "security_policy"], "cadence_days": 90},
        ]},
    ],
    "ai": {"models": [
        {"key": "hospitality-assistant", "name": "Hospitality Operations Assistant", "system_prompt": "You assist hotels, restaurants and venues with reservations, guests, housekeeping, events and F&B. Use the organization's booking, guest and property data. Service suggestions respect guest preferences.", "terminology": ["occupancy rate", "ADR", "RevPAR", "no-show rate", "housekeeping backlog", "cover count", "banquet"], "knowledge_scope": {"domains": ["hotel operations", "revenue management", "guest service", "F&B"]}, "guardrails": ["Never share guest data across organizations", "Respect guest privacy preferences"], "skills": {"summarize": "Summarize occupancy, revenue and operations health.", "recommend": "Recommend staffing and housekeeping schedules from demand.", "assist": "Answer operational questions from property data."}},
    ]},
    "kpis": [
        {"key": "occupancy_rate", "name": "Occupancy Rate", "unit": "%", "benchmark": 75},
        {"key": "adr", "name": "Average Daily Rate", "unit": "$", "benchmark": 120},
        {"key": "revpar", "name": "RevPAR", "unit": "$", "benchmark": 90},
        {"key": "housekeeping_backlog", "name": "Housekeeping Backlog", "unit": "rooms", "benchmark": 5},
        {"key": "guest_satisfaction", "name": "Guest Satisfaction", "unit": "%", "benchmark": 88},
        {"key": "no_show_rate", "name": "No-Show Rate", "unit": "%", "benchmark": 8},
    ],
    "navigation": {"label": "Hospitality", "sections": ["Reservations", "Guests", "Housekeeping", "Maintenance", "Events", "Restaurants", "Training"]},
}
