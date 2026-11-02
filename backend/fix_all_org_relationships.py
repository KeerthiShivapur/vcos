#!/usr/bin/env python
"""
Comprehensive fix: Add ALL missing Organization relationships for models with FK to organizations.id
"""
import re
import os

models_dir = r"D:\vcos1\workspace\vcos\backend\app\models"
org_file = r"D:\vcos1\workspace\vcos\backend\app\models\organization.py"

# Step 1: Find all models with ForeignKey to organizations.id and their back_populates
relationships = {}

for filename in os.listdir(models_dir):
    if not filename.endswith('.py') or filename.startswith('__'):
        continue
    filepath = os.path.join(models_dir, filename)
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except:
        continue

    # Find class name
    class_match = re.search(r'class\s+(\w+)\s*\(', content)
    if not class_match:
        continue
    class_name = class_match.group(1)

    # Find ForeignKey to organizations.id
    fk_matches = re.findall(r'ForeignKey\(["\']organizations\.id["\'][^)]*\)', content)
    if not fk_matches:
        continue

    # Find back_populates
    bp_matches = re.findall(r'back_populates\s*=\s*["\']([^"\']+)["\']', content)
    for bp in bp_matches:
        if bp not in relationships:
            relationships[bp] = []
        relationships[bp].append(class_name)

# Deduplicate
for bp in relationships:
    relationships[bp] = list(dict.fromkeys(relationships[bp]))

print(f"Found {len(relationships)} unique back_populates names")
print(f"Total relationships: {sum(len(v) for v in relationships.values())}")

# Fix model names that are wrong (e.g., OperatingModel -> AdaptiveOperatingProfile)
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
    "CalendarEventStatus": "CalendarEvent",
    "BackupKind": "Backup",
    "CompletenessDimension": "CompletenessDimension",
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
    "CompanyExperienceProfile": "CompanyExperienceProfile",
    "CapabilityLifecycleRecord": "CapabilityLifecycleRecord",
    "IntegrationConfigRecord": "IntegrationConfigRecord",
    "WorkflowConfigurationRecord": "WorkflowConfigurationRecord",
    "AdaptationRecommendationRecord": "AdaptationRecommendationRecord",
    "CompanyExperienceProfileHistory": "CompanyExperienceProfileHistory",
    "CapabilityLifecycleRecord": "CapabilityLifecycleRecord",
    "IntegrationConfigRecord": "IntegrationConfigRecord",
    "WorkflowConfigurationRecord": "WorkflowConfigurationRecord",
    "AdaptationRecommendationRecord": "AdaptationRecommendationRecord",
}

# Read the organization.py file
with open(r'D:\vcos1\workspace\vcos\backend\app\models\organization.py', 'r') as f:
    org_content = f.read()

# Find the insertion point - after the last relationship
# Look for the last relationship in Organization class
marker = "user_roles: Mapped[List[\"UserRole\"]] = relationship("
marker_pos = org_content.find(marker)
if marker_pos == -1:
    # Try alternative
    marker = "user_roles:"
    marker_pos = org_content.find(marker)

if marker_pos == -1:
    print("Could not find insertion marker!")
    exit(1)

# Find the end of that relationship block
end_pos = org_content.find(")\n", org_content.find("cascade=\"all, delete-orphan\"", org_content.find("user_roles")))
if end_pos == -1:
    print("Could not find end of user_roles block!")
    exit(1)

insert_pos = end_pos + 2

# Build new relationships
existing_attrs = {
    "users", "departments", "teams", "experience_config", "adaptive_profile",
    "adaptive_profile_versions", "capability_lifecycle_records",
    "integration_config_records", "workflow_configurations",
    "adaptation_recommendations", "experience_profile_history",
    "employees", "user_roles"
}

new_relationships = "\n"
for bp, classes in sorted(relationships.items()):
    if bp in existing_attrs:
        continue
    for cls in classes:
        fixed_model = model_name_fixes.get(cls, cls)
        new_relationships += f'    {bp}: Mapped[List["{fixed_model}"]] = relationship(back_populates="organization", cascade="all, delete-orphan")\n'

# Insert the new relationships
insert_pos = org_content.find(")\n", org_content.find("user_roles:"))
if insert_pos == -1:
    # Find end of user_roles block
    user_roles_pos = org_content.find("user_roles:")
    if user_roles_pos != -1:
        end_brace = org_content.find(")\n", org_content.find("cascade=\"all, delete-orphan\"", user_roles_pos))
        if end_brace != -1:
            insert_pos = end_brace + 2

if insert_pos == -1:
    print("Could not determine insert position")
    exit(1)

new_content = org_content[:insert_pos] + new_relationships + org_content[insert_pos:]

with open(r'D:\vcos1\workspace\vcos\backend\app\models\organization.py', 'w') as f:
    f.write(new_content)

print(f"Successfully added {sum(len(v) for v in relationships.values()) - len(existing_attrs)} new relationships")