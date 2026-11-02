with open('tests/acceptance/test_acceptance_real.py', 'r') as f:
    content = f.read()

# Add ScenarioStatus import
content = content.replace(
    'from tests.acceptance.matrix_runner_real import (\n    AcceptanceMatrixRunner,\n    run_acceptance_matrix_real,\n    InvariantVerifier,\n    InvariantStatus,\n)',
    'from tests.acceptance.matrix_runner_real import (\n    AcceptanceMatrixRunner,\n    run_acceptance_matrix_real,\n    InvariantVerifier,\n    InvariantStatus,\n    ScenarioStatus,\n)'
)

with open('tests/acceptance/test_acceptance_real.py', 'w') as f:
    f.write(content)

print('Added ScenarioStatus import')