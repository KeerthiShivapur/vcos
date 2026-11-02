with open('app/intelligence/company_context.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add contradiction kinds to _EVIDENCE_META - using a more robust approach
# Find the closing brace of _EVIDENCE_META
old = '''    "template": {"source": "templates", "url": "/templates/{}"},
}'''

new = '''    "template": {"source": "templates", "url": "/templates/{}"},
    # Contradiction kinds for Gate 6-E
    "decision_contradiction": {"source": "company_decision_contradictions", "url": "/contradictions/decision/{}"},
    "objective_contradiction": {"source": "objective_contradictions", "url": "/contradictions/objective/{}"},
}'''

content = content.replace(old, new)

with open('app/intelligence/company_context.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Added contradiction kinds to _EVIDENCE_META')