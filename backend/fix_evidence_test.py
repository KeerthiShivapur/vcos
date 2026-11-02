with open('tests/acceptance/test_acceptance_real.py', 'r') as f:
    content = f.read()

# Fix test_evidence_generation to call save_results
content = content.replace(
    '''result = await runner.run()
            \n            # Check evidence file was created\n            evidence_files = [f for f in os.listdir(tmpdir) if f.startswith("acceptance_matrix_")]''',
    '''result = await runner.run()\n            runner.save_results(result)\n            \n            # Check evidence file was created\n            evidence_files = [f for f in os.listdir(tmpdir) if f.startswith("acceptance_matrix_")]'''
)

with open('tests/acceptance/test_acceptance_real.py', 'w') as f:
    f.write(content)

print('Fixed test_evidence_generation to call save_results')