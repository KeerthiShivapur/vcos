with open('tests/acceptance/test_integration_adversarial.py', 'r') as f:
    content = f.read()

# Add force auth header to all security tests
old1 = '''        headers = {
            "x-hub-signature-256": "sha256=invalid_signature",
            "x-github-delivery": f"delivery-{uuid.uuid4().hex[:8]}",
        }'''

new1 = '''        headers = {
            "x-hub-signature-256": "sha256=invalid_signature",
            "x-github-delivery": f"delivery-{uuid.uuid4().hex[:8]}",
            "x-vcos-force-auth": "true",
        }'''

old2 = '''        headers = {
            "x-slack-signature": "v0=invalid_signature",
            "x-slack-request-timestamp": str(int(utcnow().timestamp())),
            "x-slack-request-id": f"req-{uuid.uuid4().hex[:8]}",
        }'''

new2 = '''        headers = {
            "x-slack-signature": "v0=invalid_signature",
            "x-slack-request-timestamp": str(int(utcnow().timestamp())),
            "x-slack-request-id": f"req-{uuid.uuid4().hex[:8]}",
            "x-vcos-force-auth": "true",
        }'''

old3 = '''        headers = {
            "x-slack-signature": "v0=valid_signature",
            "x-slack-request-timestamp": str(int(utcnow().timestamp())),
            "x-slack-request-id": f"req-{uuid.uuid4().hex[:8]}",
        }'''

new3 = '''        headers = {
            "x-slack-signature": "v0=valid_signature",
            "x-slack-request-timestamp": str(int(utcnow().timestamp())),
            "x-slack-request-id": f"req-{uuid.uuid4().hex[:8]}",
            "x-vcos-force-auth": "true",
        }'''

content = content.replace(old1, new1)
content = content.replace(old2, new2)
content = content.replace(old3, new3)

with open('tests/acceptance/test_integration_adversarial.py', 'w') as f:
    f.write(content)
print('Done')