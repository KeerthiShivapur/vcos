import re

with open('tests/acceptance/scenario_builder.py', 'r') as f:
    content = f.read()

# Find scenario types
scenario_types = re.findall(r'ScenarioType\.(\w+)', content)
print('Scenario types:', set(scenario_types))

# Find action mappings
action_mappings = re.findall(r'"action":\s*"([^"]+)"', content)
print('Actions:', set(action_mappings))