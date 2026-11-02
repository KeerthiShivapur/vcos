with open('tests/acceptance/test_integration_adversarial.py', 'r') as f:
    content = f.read()

# Fix test_6_out_of_order_webhook_handled - change repository ID for second event to 124
old = '''        # Event 2: Issue closed (newer timestamp)
        payload2 = {
            "action": "closed",
            "issue": {"id": 456, "number": 1, "title": "Issue 1", "state": "closed"},
            "repository": {"id": 123},
        }'''

new = '''        # Event 2: Issue closed (newer timestamp)
        payload2 = {
            "action": "closed",
            "issue": {"id": 457, "number": 1, "title": "Issue 1", "state": "closed"},
            "repository": {"id": 124},
        }'''

content = content.replace(old, new)

with open('tests/acceptance/test_integration_adversarial.py', 'w') as f:
    f.write(content)
print('Fixed')