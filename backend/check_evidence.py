import json
import sys

with open('output.json', 'r') as f:
    data = f.read()

# Find the evidence section
start = data.find('"evidence"')
if start > 0:
    # Find the matching closing brace
    brace_count = 0
    in_string = False
    escape = False
    for i, ch in enumerate(data[start:]):
        if escape:
            escape = False
            continue
        if ch == '\\':
            escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
        if not in_string:
            if ch == '{':
                brace_count += 1
            elif ch == '}':
                brace_count -= 1
                if brace_count == 0:
                    evidence_str = data[start:start+i+1]
                    evidence = json.loads(evidence_str)
                    domains = ['environment', 'generation', 'structural_integrity', 'tenant_isolation', 'temporal', 
                               'provenance', 'epistemic', 'governance', 'company_brain', 'performance', 
                               'resources', 'recovery', 'promotion', 'concurrency']
                    for domain in domains:
                        has_evidence = evidence.get(domain) is not None
                        status = 'YES' if has_evidence else 'MISSING'
                        print(domain + ': ' + status)
                    break