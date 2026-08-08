"""Prompt templates for the organization-aware AI layers."""

SYSTEM_CORE = (
    "You are the AI operating layer of {organization_name}, a Virtual Company "
    "Operating System. You understand the company: its people, departments, "
    "projects, knowledge, goals and history. Help employees complete work."
)

DAILY_SUMMARY = "Summarize what happened yesterday for {full_name}."

EXPERT_FINDER = "Find the best expert for '{topic}' and explain why."

DECISION_SUPPORT = "Evaluate the decision '{decision}' with pros, cons and risks."

KNOWLEDGE_EXPLAIN = "Explain '{topic}' using company knowledge."
