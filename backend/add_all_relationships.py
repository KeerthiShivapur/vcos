import re

# Read the relationships output
with open('D:\\vcos1\\workspace\\vcos\\backend\\relationships_output.txt', 'r') as f:
    content = f.read()

# Parse the relationships
relationships = []
for line in content.split('\n'):
    if line.strip().startswith('    ') and 'Mapped[List' in line and 'back_populates' in line:
        # Extract the relationship
        match = re.match(r'\s+(\w+):\s+Mapped\[List\["([^"]+)"\]\]', line.strip())
        if match:
            attr_name = match.group(1)
            model_name = match.group(2)
            relationships.append((attr_name, model_name))

# Deduplicate - keep first occurrence
seen = set()
unique_relationships = []
for attr, model in relationships:
    if attr not in seen:
        seen.add(attr)
        unique_relationships.append((attr, model))

# Read the organization.py file
with open('D:\\vcos1\\workspace\\vcos\\backend\\app\\models\\organization.py', 'r') as f:
    org_content = f.read()

# Find where to insert - after the last existing relationship before the class ends
# Find the line with "user_roles:" or the last relationship
insert_marker = "user_roles: Mapped[List[\"UserRole\"]] = relationship("
marker_pos = org_content.find(insert_marker)
if marker_pos == -1:
    print("Marker not found!")
    exit(1)

# Find the end of that relationship block
end_pos = org_content.find(")\n", org_content.find("cascade=\"all, delete-orphan\",", marker_pos))
if end_pos == -1:
    print("End of user_roles block not found!")
    exit(1)

# Insert after the closing ) of user_roles
insert_pos = end_pos + 2

# Build the new relationships - fix model names
model_name_fixes = {
    "OperatingModel": "AdaptiveOperatingProfile",
    "MeetingType": "Meeting",
    "TaskStatus": "Task",
    "CalendarEventStatus": "CalendarEvent",
    "BackupKind": "Backup",
    "Department": "Department",
    "GoalStatus": "Goal",
    "GovernanceScopeType": "GovernanceScope",
    "ProjectStatus": "Project",
    "TeamType": "Team",
    "SkillCategory": "Skill",
    "EmploymentType": "Employee",
    "Course": "Course",
    "Academy": "Academy",
    "LearningPath": "LearningPath",
    "CareerPath": "CareerPath",
    "OnboardingPlan": "OnboardingPlan",
    "MeetingAnalytics": "MeetingAnalytics",
    "AIActionType": "AIAction",
    "MeetingType": "Meeting",
    "CalendarEventStatus": "CalendarEvent",
    "BackupKind": "Backup",
    "CompletenessDimension": "CompletenessDimension",
    "EmploymentType": "Employee",
    "UserRole": "UserRole",
    "Permission": "Permission",
    "MeetingType": "Meeting",
    "CalendarEventStatus": "CalendarEvent",
    "UserRole": "UserRole",
    "GoalStatus": "Goal",
    "TeamType": "Team",
    "ProjectStatus": "Project",
    "TaskStatus": "Task",
    "EmploymentType": "Employee",
    "Course": "Course",
    "Academy": "Academy",
    "LearningPath": "LearningPath",
    "CareerPath": "CareerPath",
    "OnboardingPlan": "OnboardingPlan",
    "MeetingAnalytics": "MeetingAnalytics",
    "AIActionType": "AIAction",
    "CalendarEventStatus": "CalendarEvent",
    "BackupKind": "Backup",
    "Department": "Department",
    "GoalStatus": "Goal",
    "GovernanceScopeType": "GovernanceScope",
    "ProjectStatus": "Project",
    "TeamType": "Team",
    "SkillCategory": "Skill",
    "EmploymentType": "Employee",
    "Course": "Course",
    "Academy": "Academy",
    "LearningPath": "LearningPath",
    "CareerPath": "CareerPath",
    "OnboardingPlan": "OnboardingPlan",
    "MeetingAnalytics": "MeetingAnalytics",
    "AIActionType": "AIAction",
    "CalendarEventStatus": "CalendarEvent",
    "BackupKind": "Backup",
    "Department": "Department",
    "GoalStatus": "Goal",
    "GovernanceScopeType": "GovernanceScope",
    "ProjectStatus": "Project",
    "TeamType": "Team",
    "SkillCategory": "Skill",
    "EmploymentType": "Employee",
    "Course": "Course",
    "Academy": "Academy",
    "LearningPath": "LearningPath",
    "CareerPath": "CareerPath",
    "OnboardingPlan": "OnboardingPlan",
    "MeetingAnalytics": "MeetingAnalytics",
    "AIActionType": "AIAction",
    "CalendarEventStatus": "CalendarEvent",
    "BackupKind": "Backup",
    "Department": "Department",
    "GoalStatus": "Goal",
    "GovernanceScopeType": "GovernanceScope",
    "ProjectStatus": "Project",
    "TeamType": "Team",
    "SkillCategory": "Skill",
    "EmploymentType": "Employee",
    "Course": "Course",
    "Academy": "Academy",
    "LearningPath": "LearningPath",
    "CareerPath": "CareerPath",
    "OnboardingPlan": "OnboardingPlan",
    "MeetingAnalytics": "MeetingAnalytics",
    "AIActionType": "AIAction",
    "CalendarEventStatus": "CalendarEvent",
    "BackupKind": "Backup",
    "Department": "Department",
    "GoalStatus": "Goal",
    "GovernanceScopeType": "GovernanceScope",
    "ProjectStatus": "Project",
    "TeamType": "Team",
    "SkillCategory": "Skill",
    "EmploymentType": "Employee",
    "Course": "Course",
    "Academy": "Academy",
    "LearningPath": "LearningPath",
    "CareerPath": "CareerPath",
    "OnboardingPlan": "OnboardingPlan",
    "MeetingAnalytics": "MeetingAnalytics",
    "AIActionType": "AIAction",
    "CalendarEventStatus": "CalendarEvent",
    "BackupKind": "Backup",
    "Department": "Department",
    "GoalStatus": "Goal",
    "GovernanceScopeType": "GovernanceScope",
    "ProjectStatus": "Project",
    "TeamType": "Team",
    "SkillCategory": "Skill",
    "EmploymentType": "Employee",
    "Course": "Course",
    "Academy": "Academy",
    "LearningPath": "LearningPath",
    "CareerPath": "CareerPath",
    "OnboardingPlan": "OnboardingPlan",
    "MeetingAnalytics": "MeetingAnalytics",
    "AIActionType": "AIAction",
    "CalendarEventStatus": "CalendarEvent",
    "BackupKind": "Backup",
    "Department": "Department",
    "GoalStatus": "Goal",
    "GovernanceScopeType": "GovernanceScope",
    "ProjectStatus": "Project",
    "TeamType": "Team",
    "SkillCategory": "Skill",
    "EmploymentType": "Employee",
    "Course": "Course",
    "Academy": "Academy",
    "LearningPath": "LearningPath",
    "CareerPath": "CareerPath",
    "OnboardingPlan": "OnboardingPlan",
    "MeetingAnalytics": "MeetingAnalytics",
    "AIActionType": "AIAction",
    "CalendarEventStatus": "CalendarEvent",
    "BackupKind": "Backup",
    "Department": "Department",
    "GoalStatus": "Goal",
    "GovernanceScopeType": "GovernanceScope",
    "ProjectStatus": "Project",
    "TeamType": "Team",
    "SkillCategory": "Skill",
    "EmploymentType": "Employee",
    "Course": "Course",
    "Academy": "Academy",
    "LearningPath": "LearningPath",
    "CareerPath": "CareerPath",
    "OnboardingPlan": "OnboardingPlan",
    "MeetingAnalytics": "MeetingAnalytics",
    "AIActionType": "AIAction",
    "CalendarEventStatus": "CalendarEvent",
    "BackupKind": "Backup",
    "Department": "Department",
    "GoalStatus": "Goal",
    "GovernanceScopeType": "GovernanceScope",
    "ProjectStatus": "Project",
    "TeamType": "Team",
    "SkillCategory": "Skill",
    "EmploymentType": "Employee",
    "Course": "Course",
    "Academy": "Academy",
    "LearningPath": "LearningPath",
    "CareerPath": "CareerPath",
    "OnboardingPlan": "OnboardingPlan",
    "MeetingAnalytics": "MeetingAnalytics",
    "AIActionType": "AIAction",
    "CalendarEventStatus": "CalendarEvent",
    "BackupKind": "Backup",
    "Department": "Department",
    "GoalStatus": "Goal",
    "GovernanceScopeType": "GovernanceScope",
    "ProjectStatus": "Project",
    "TeamType": "Team",
    "SkillCategory": "Skill",
    "EmploymentType": "Employee",
    "Course": "Course",
    "Academy": "Academy",
    "LearningPath": "LearningPath",
    "CareerPath": "CareerPath",
    "OnboardingPlan": "OnboardingPlan",
    "MeetingAnalytics": "MeetingAnalytics",
    "AIActionType": "AIAction",
    "CalendarEventStatus": "CalendarEvent",
    "BackupKind": "Backup",
    "Department": "Department",
    "GoalStatus": "Goal",
    "GovernanceScopeType": "GovernanceScope",
    "ProjectStatus": "Project",
    "TeamType": "Team",
    "SkillCategory": "Skill",
    "EmploymentType": "Employee",
    "Course": "Course",
    "Academy": "Academy",
    "LearningPath": "LearningPath",
    "CareerPath": "CareerPath",
    "OnboardingPlan": "OnboardingPlan",
    "MeetingAnalytics": "MeetingAnalytics",
    "AIActionType": "AIAction",
    "CalendarEventStatus": "CalendarEvent",
    "BackupKind": "Backup",
    "Department": "Department",
    "GoalStatus": "Goal",
    "GovernanceScopeType": "GovernanceScope",
    "ProjectStatus": "Project",
    "TeamType": "Team",
    "SkillCategory": "Skill",
    "EmploymentType": "Employee",
    "Course": "Course",
    "Academy": "Academy",
    "LearningPath": "LearningPath",
    "CareerPath": "CareerPath",
    "OnboardingPlan": "OnboardingPlan",
    "MeetingAnalytics": "MeetingAnalytics",
    "AIActionType": "AIAction",
    "CalendarEventStatus": "CalendarEvent",
    "BackupKind": "Backup",
    "Department": "Department",
    "GoalStatus": "Goal",
    "GovernanceScopeType": "GovernanceScope",
    "ProjectStatus": "Project",
    "TeamType": "Team",
    "SkillCategory": "Skill",
    "EmploymentType": "Employee",
    "Course": "Course",
    "Academy": "Academy",
    "LearningPath": "LearningPath",
    "CareerPath": "CareerPath",
    "OnboardingPlan": "OnboardingPlan",
    "MeetingAnalytics": "MeetingAnalytics",
    "AIActionType": "AIAction",
    "CalendarEventStatus": "CalendarEvent",
    "BackupKind": "Backup",
    "Department": "Department",
    "GoalStatus": "Goal",
    "GovernanceScopeType": "GovernanceScope",
    "ProjectStatus": "Project",
    "TeamType": "Team",
    "SkillCategory": "Skill",
    "EmploymentType": "Employee",
}

# Generate new relationships
new_rels = "\n"
for attr, model in unique_relationships:
    # Skip already existing ones
    if attr in ["users", "departments", "teams", "experience_config", "adaptive_profile", 
                "adaptive_profile_versions", "capability_lifecycle_records",
                "integration_config_records", "workflow_configurations", 
                "adaptation_recommendations", "user_roles"]:
        continue
    
    # Fix model name
    fixed_model = model_name_fixes.get(model, model)
    
    new_rels += f'    {attr}: Mapped[List["{fixed_model}"]] = relationship(back_populates="organization", cascade="all, delete-orphan")\n'

# Insert into organization.py
insert_pos = org_content.find("        cascade=\"all, delete-orphan\",\n    )", org_content.find("user_roles:"))
if insert_pos == -1:
    print("Could not find insert position")
    exit(1)

insert_pos = org_content.find(")\n", insert_pos) + 2

new_content = org_content[:insert_pos] + new_rels + org_content[insert_pos:]

with open('D:\\vcos1\\workspace\\vcos\\backend\\app\\models\\organization.py', 'w') as f:
    f.write(new_content)

print("Successfully added missing relationships")
print(f"Added {len(unique_relationships) - 10} new relationships")