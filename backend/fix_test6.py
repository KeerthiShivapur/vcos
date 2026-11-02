with open('tests/acceptance/test_integration_adversarial.py', 'r') as f:
    content = f.read()

# Fix test_6_out_of_order_webhook_handled - add proper HMAC signatures
old = '''        # Event 1: Issue opened (older timestamp)
        payload1 = {
            "action": "opened",
            "issue": {"id": 456, "number": 1, "title": "Issue 1", "state": "open"},
            "repository": {"id": 123},
        }
        headers1 = {"x-hub-signature-256": "sha256=dummy", "x-github-delivery": f"d1-{uuid.uuid4().hex[:8]}"}
        
        # Event 2: Issue closed (newer timestamp)
        payload2 = {
            "action": "closed",
            "issue": {"id": 456, "number": 1, "title": "Issue 1", "state": "closed"},
            "repository": {"id": 123},
        }
        headers2 = {"x-hub-signature-256": "sha256=dummy", "x-github-delivery": f"d2-{uuid.uuid4().hex[:8]}"}'''

new = '''        # Event 1: Issue opened (older timestamp)
        payload1 = {
            "action": "opened",
            "issue": {"id": 456, "number": 1, "title": "Issue 1", "state": "open"},
            "repository": {"id": 123},
        }
        import hmac
        import hashlib
        sig1 = "sha256=" + hmac.new(b"test_secret", json.dumps(payload1, separators=(",", ":")).encode(), hashlib.sha256).hexdigest()
        headers1 = {"x-hub-signature-256": sig1, "x-github-delivery": f"d1-{uuid.uuid4().hex[:8]}"}
        
        # Event 2: Issue closed (newer timestamp)
        payload2 = {
            "action": "closed",
            "issue": {"id": 456, "number": 1, "title": "Issue 1", "state": "closed"},
            "repository": {"id": 123},
        }
        sig2 = "sha256=" + hmac.new(b"test_secret", json.dumps(payload2, separators=(",", ":")).encode(), hashlib.sha256).hexdigest()
        headers2 = {"x-hub-signature-256": sig2, "x-github-delivery": f"d2-{uuid.uuid4().hex[:8]}"}'''

content = content.replace(old, new)

with open('tests/acceptance/test_integration_adversarial.py', 'w') as f:
    f.write(content)
print('Fixed')