"""Phase 15 — Enterprise Platform, Extensibility & Global Administration.

Covers the enterprise console: identity (SSO/OAuth2/OIDC/SAML/LDAP, SCIM,
MFA, passkeys, devices, auth policies), plugin lifecycle & isolation, the
marketplace, the API gateway (keys, rate limits, versioning), integration
connections, monitoring & observability, the security center, compliance,
licensing, feature flags, governed AI, RBAC gating, multi-tenant isolation,
universal search and the Phase 15 workers.
"""

import pytest

from tests.conftest import register_org

VALID_MANIFEST = {
    "version": "1.0.0",
    "author": "VCOS Labs",
    "category": "crm",
    "description": "A plugin that tracks customer sentiment.",
    "permissions": ["crm:read"],
    "sandbox": True,
    "verified": True,
    "scanned": True,
    "payload": {
        "entry": "main",
        "code": "def main(ctx):\n    return {'status': 'ok'}\n",
    },
}

DANGEROUS_MANIFEST = {
    "version": "1.0.0",
    "description": "Rogue plugin.",
    "payload": {
        "entry": "main",
        "code": "import os\nos.system('rm -rf /')\n",
    },
}


async def _invite_employee(client, headers, email, role="employee"):
    invite = await client.post(
        "/api/v1/users/invite",
        json={"email": email, "full_name": "Emp Worker", "role": role},
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    response = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": invite.json()["token"], "full_name": "Emp Worker", "password": "EmpPass123!"},
    )
    assert response.status_code == 201, response.text
    return {"headers": {"Authorization": f"Bearer {response.json()['access_token']}"},
            "user": response.json()["user"]}


async def _create_provider(client, headers, name="Okta", provider_type="oidc", **overrides):
    payload = {
        "name": name,
        "provider_type": provider_type,
        "config": {
            "issuer": "https://okta.example.com",
            "client_id": "abc123",
            "client_secret": "s3cret",
        },
    }
    payload.update(overrides)
    response = await client.post(
        "/api/v1/enterprise/identity/providers", json=payload, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _install_plugin(client, headers, plugin_key="sentiment", manifest=None):
    response = await client.post(
        "/api/v1/enterprise/plugins",
        json={"plugin_key": plugin_key, "name": "Sentiment", "manifest": manifest or VALID_MANIFEST},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _event_names(client, headers):
    events = (await client.get("/api/v1/events?limit=50", headers=headers)).json()
    return {e["name"] for e in events.get("items", events)}


# ------------------------------------------------------- identity: SSO providers


async def test_identity_provider_crud_and_sso_flow(client):
    org = await register_org(client, email="p15id@test.co")
    headers = org["headers"]

    saml = await _create_provider(
        client, headers, name="Azure AD", provider_type="saml",
        config={"entity_id": "https://sts.azure.example", "sso_url": "https://login.example",
                "certificate": "MII..."},
    )
    assert saml["provider_type"] == "saml"

    missing = await client.post(
        "/api/v1/enterprise/identity/providers",
        json={"name": "Bad LDAP", "provider_type": "ldap", "config": {"server_url": "ldap://x"}},
        headers=headers,
    )
    assert missing.status_code == 400
    assert "base_dn" in missing.json()["detail"]

    initiated = await client.post(
        "/api/v1/enterprise/sso/initiate",
        json={"provider_id": saml["id"], "redirect_uri": "/dashboard"},
        headers=headers,
    )
    assert initiated.status_code == 200, initiated.text
    body = initiated.json()
    assert body["state"] and body["signature"] and body["auth_url"] == "https://login.example"

    completed = await client.post(
        "/api/v1/enterprise/sso/complete",
        json={
            "provider_id": saml["id"],
            "state": body["state"],
            "signature": body["signature"],
            "subject": "sub-ada-owner",
            "email": org["user"]["email"],
        },
        headers=headers,
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "ok"
    assert completed.json()["user_id"] == org["user"]["id"]

    bindings = (await client.get("/api/v1/enterprise/identity/bindings", headers=headers)).json()
    assert any(b["external_subject"] == "sub-ada-owner" for b in bindings)

    deleted = await client.delete(
        f"/api/v1/enterprise/identity/providers/{saml['id']}", headers=headers
    )
    assert deleted.status_code == 204


async def test_sso_assertion_endpoint(client):
    org = await register_org(client, email="p15sso@test.co")
    headers = org["headers"]
    provider = await _create_provider(client, headers, name="Google", provider_type="oidc")

    initiated = await client.post(
        "/api/v1/enterprise/sso/initiate",
        json={"provider_id": provider["id"], "redirect_uri": "/"},
        headers=headers,
    )
    assert initiated.status_code == 200, initiated.text

    response = await client.post(
        "/api/v1/enterprise/sso",
        json={
            "provider_id": provider["id"],
            "subject": "google-ada",
            "email": org["user"]["email"],
            "state": initiated.json()["state"],
            "signature": initiated.json()["signature"],
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ok"


async def test_mfa_passkeys_and_devices(client):
    import hashlib
    from datetime import datetime, timezone

    org = await register_org(client, email="p15mfa@test.co")
    headers = org["headers"]

    enrolled = (await client.post("/api/v1/enterprise/identity/mfa/enroll", headers=headers)).json()
    assert enrolled["mfa_method"] == "totp"
    secret = enrolled["mfa_secret"]

    hour = datetime.now(timezone.utc).hour
    valid_code = f"{int(hashlib.sha256(f'{secret}:{hour}'.encode()).hexdigest(), 16) % 1_000_000:06d}"
    wrong_code = "000000" if valid_code != "000000" else "000001"

    bad = await client.post(
        "/api/v1/enterprise/identity/mfa/verify",
        json={"code": wrong_code},
        headers=headers,
    )
    assert bad.status_code == 400

    good = await client.post(
        "/api/v1/enterprise/identity/mfa/verify",
        json={"code": valid_code},
        headers=headers,
    )
    assert good.status_code == 200
    assert good.json()["mfa_enabled"] is True

    passkey = await client.post(
        "/api/v1/enterprise/identity/passkeys",
        json={"credential_id": "cred-passkey-1"},
        headers=headers,
    )
    assert passkey.status_code == 200
    assert "cred-passkey-1" in passkey.json()["passkeys"]

    device = await client.post(
        "/api/v1/enterprise/identity/devices",
        json={"name": "Work laptop", "device_type": "laptop"},
        headers=headers,
    )
    assert device.status_code == 201
    devices = (await client.get("/api/v1/enterprise/identity/devices", headers=headers)).json()
    assert len(devices) == 1 and devices[0]["trusted"] is True


async def test_authentication_policy_and_ip_restrictions(client):
    org = await register_org(client, email="p15policy@test.co")
    headers = org["headers"]

    policy = await client.post(
        "/api/v1/enterprise/identity/policies",
        json={"name": "HQ only", "mfa_required": True, "session_timeout_minutes": 60,
              "ip_restrictions": ["203.0.113."]},
        headers=headers,
    )
    assert policy.status_code == 201, policy.text

    allowed = await client.post(
        "/api/v1/enterprise/security/check-ip", json={"ip": "203.0.113.10"}, headers=headers
    )
    assert allowed.status_code == 200 and allowed.json()["allowed"] is True

    blocked = await client.post(
        "/api/v1/enterprise/security/check-ip", json={"ip": "198.51.100.9"}, headers=headers
    )
    assert blocked.status_code == 200 and blocked.json()["allowed"] is False

    events = (await client.get("/api/v1/enterprise/security/events", headers=headers)).json()
    assert any(e["event_type"] == "ip.blocked" for e in events)


# ------------------------------------------------------------------------- SCIM


async def test_scim_user_provisioning(client):
    org = await register_org(client, email="p15scim@test.co")
    headers = org["headers"]

    created = await client.post(
        "/api/v1/enterprise/scim/users",
        json={
            "userName": "alice.scim",
            "emails": [{"value": "alice@scim.test.co", "primary": True}],
            "active": True,
            "externalId": "ext-alice-1",
            "displayName": "Alice Scim",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["vcos_user_id"]

    listed = (await client.get("/api/v1/enterprise/scim/users", headers=headers)).json()
    assert listed["totalResults"] == 1

    fetched = await client.get(
        f"/api/v1/enterprise/scim/users/ext-alice-1", headers=headers
    )
    assert fetched.status_code == 200
    assert fetched.json()["userName"] == "alice.scim"

    deactivated = await client.patch(
        "/api/v1/enterprise/scim/users/ext-alice-1",
        json={"active": False},
        headers=headers,
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["active"] is False

    deleted = await client.delete("/api/v1/enterprise/scim/users/ext-alice-1", headers=headers)
    assert deleted.status_code == 204
    gone = await client.get("/api/v1/enterprise/scim/users/ext-alice-1", headers=headers)
    assert gone.status_code == 404


async def test_scim_groups(client):
    org = await register_org(client, email="p15scimg@test.co")
    headers = org["headers"]

    created = await client.post(
        "/api/v1/enterprise/scim/groups",
        json={
            "externalId": "grp-engineers",
            "displayName": "Engineers",
            "members": [{"value": "ext-alice-1", "type": "User"}],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["members"][0]["value"] == "ext-alice-1"

    groups = (await client.get("/api/v1/enterprise/scim/groups", headers=headers)).json()
    assert groups["totalResults"] == 1

    deleted = await client.delete("/api/v1/enterprise/scim/groups/grp-engineers", headers=headers)
    assert deleted.status_code == 204


# --------------------------------------------------------------- plugin lifecycle


async def test_plugin_lifecycle_and_tenant_isolation(client):
    org = await register_org(client, email="p15plugin@test.co")
    headers = org["headers"]

    plugin = await _install_plugin(client, headers)
    assert plugin["status"] == "installed"
    assert plugin["scan_status"] == "clean"
    plugin_id = plugin["id"]

    disabled = await client.post(
        f"/api/v1/enterprise/plugins/{plugin_id}/disable", headers=headers
    )
    assert disabled.status_code == 200 and disabled.json()["status"] == "disabled"

    enabled = await client.post(
        f"/api/v1/enterprise/plugins/{plugin_id}/enable", headers=headers
    )
    assert enabled.status_code == 200 and enabled.json()["status"] == "installed"

    updated = await client.post(
        f"/api/v1/enterprise/plugins/{plugin_id}/update",
        json={"version": "2.1.0", "changelog": "Better scoring",
              "payload": {"entry": "main", "code": "def main(ctx):\n    return {'v': 2}\n"}},
        headers=headers,
    )
    assert updated.status_code == 200 and updated.json()["version"] == "2.1.0"

    settings = await client.patch(
        f"/api/v1/enterprise/plugins/{plugin_id}/settings",
        json={"settings": {"threshold": 0.8}},
        headers=headers,
    )
    assert settings.status_code == 200
    assert settings.json()["settings"]["threshold"] == 0.8

    # isolation: a second org never sees the plugin
    other = await register_org(client, email="p15plugin2@test.co")
    other_plugins = (await client.get("/api/v1/enterprise/plugins", headers=other["headers"])).json()
    assert other_plugins == []

    removed = await client.delete(f"/api/v1/enterprise/plugins/{plugin_id}", headers=headers)
    assert removed.status_code == 204
    assert (await client.get("/api/v1/enterprise/plugins", headers=headers)).json() == []


async def test_plugin_sandbox_scan_rejects_dangerous_payload(client):
    org = await register_org(client, email="p15rogue@test.co")
    headers = org["headers"]

    response = await client.post(
        "/api/v1/enterprise/plugins",
        json={"plugin_key": "rogue", "name": "Rogue", "manifest": DANGEROUS_MANIFEST},
        headers=headers,
    )
    assert response.status_code == 400
    assert "sandbox escape" in response.json()["detail"]


async def test_plugin_update_rejects_dangerous_payload(client):
    org = await register_org(client, email="p15rogue2@test.co")
    headers = org["headers"]
    plugin = await _install_plugin(client, headers, plugin_key="trusted")

    response = await client.post(
        f"/api/v1/enterprise/plugins/{plugin['id']}/update",
        json={"version": "9.0.0", "payload": {"entry": "main",
                                              "code": "eval('1+1')\n"}},
        headers=headers,
    )
    assert response.status_code == 400
    assert "eval" in response.json()["detail"]


# ------------------------------------------------------------------- marketplace


async def test_marketplace_publish_install_and_reviews(client):
    org = await register_org(client, email="p15market@test.co")
    headers = org["headers"]

    published = await client.post(
        "/api/v1/enterprise/marketplace/items",
        json={
            "plugin_key": "sentiment-v2",
            "name": "Sentiment Pro",
            "description": "Deep customer sentiment.",
            "category": "crm",
            "price": 9.99,
            "version": "2.0.0",
            "manifest": VALID_MANIFEST,
        },
        headers=headers,
    )
    assert published.status_code == 201, published.text
    item_id = published.json()["id"]

    items = (await client.get("/api/v1/enterprise/marketplace/items", headers=headers)).json()
    assert any(i["id"] == item_id for i in items)

    installed = await client.post(
        f"/api/v1/enterprise/marketplace/items/{item_id}/install", headers=headers
    )
    assert installed.status_code == 201, installed.text
    assert installed.json()["plugin_key"] == "sentiment-v2"
    assert installed.json()["status"] == "installed"

    duplicate = await client.post(
        f"/api/v1/enterprise/marketplace/items/{item_id}/install", headers=headers
    )
    assert duplicate.status_code == 400

    reviewed = await client.post(
        f"/api/v1/enterprise/marketplace/items/{item_id}/reviews",
        json={"rating": 5, "comment": "Love it"},
        headers=headers,
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["rating"] == 5.0
    assert reviewed.json()["review_count"] == 1

    reviewed2 = await client.post(
        f"/api/v1/enterprise/marketplace/items/{item_id}/reviews",
        json={"rating": 1},
        headers=headers,
    )
    assert reviewed2.json()["rating"] == 1.0

    item = await client.get(
        f"/api/v1/enterprise/marketplace/items/{item_id}", headers=headers
    )
    assert item.json()["downloads"] == 1
    assert item.json()["review_count"] == 1


# -------------------------------------------------------------------- API gateway


async def test_api_key_issue_authenticate_rotate_revoke(client):
    org = await register_org(client, email="p15key@test.co")
    headers = org["headers"]

    created = await client.post(
        "/api/v1/enterprise/api-keys",
        json={"name": "Integrations", "scopes": ["crm:read", "finance:read"]},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    key_id = created.json()["id"]
    raw_key = created.json()["api_key"]
    assert raw_key.startswith("vcos_")

    checked = await client.post(
        "/api/v1/enterprise/gateway/check", json={"api_key": raw_key}, headers=headers
    )
    assert checked.status_code == 200, checked.text
    assert checked.json()["organization_id"] == org["organization"]["id"]
    assert checked.json()["rate_limit"]["allowed"] is True

    versions = (await client.get("/api/v1/enterprise/gateway/versions", headers=headers)).json()
    assert versions["current"] == "v1" and versions["header"] == "X-API-Key"

    rotated = await client.post(
        f"/api/v1/enterprise/api-keys/{key_id}/rotate", headers=headers
    )
    assert rotated.status_code == 200, rotated.text
    new_key = rotated.json()["api_key"]
    assert new_key != raw_key

    old_fails = await client.post(
        "/api/v1/enterprise/gateway/check", json={"api_key": raw_key}, headers=headers
    )
    assert old_fails.status_code == 401
    new_ok = await client.post(
        "/api/v1/enterprise/gateway/check", json={"api_key": new_key}, headers=headers
    )
    assert new_ok.status_code == 200

    revoked = await client.delete(f"/api/v1/enterprise/api-keys/{key_id}", headers=headers)
    assert revoked.status_code == 204
    gone = await client.post(
        "/api/v1/enterprise/gateway/check", json={"api_key": new_key}, headers=headers
    )
    assert gone.status_code == 401


async def test_api_gateway_rate_limiting(client):
    from app.enterprise.api_gateway import api_gateway_service

    api_gateway_service.reset_rate_limits()
    org = await register_org(client, email="p15ratelimit@test.co")
    headers = org["headers"]

    created = await client.post(
        "/api/v1/enterprise/api-keys",
        json={"name": "Limited", "rate_limit_per_minute": 3},
        headers=headers,
    )
    raw_key = created.json()["api_key"]

    for _ in range(3):
        ok = await client.post(
            "/api/v1/enterprise/gateway/check", json={"api_key": raw_key}, headers=headers
        )
        assert ok.status_code == 200

    denied = await client.post(
        "/api/v1/enterprise/gateway/check", json={"api_key": raw_key}, headers=headers
    )
    assert denied.status_code == 429


# ----------------------------------------------------------------- integrations


async def test_integration_connection_lifecycle(client):
    org = await register_org(client, email="p15int@test.co")
    headers = org["headers"]

    created = await client.post(
        "/api/v1/enterprise/integrations",
        json={
            "name": "Zapier",
            "provider": "zapier",
            "kind": "webhook",
            "config": {"url": "https://hooks.zapier.example/abc"},
            "auth_type": "api_key",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    connection_id = created.json()["id"]

    invalid = await client.post(
        "/api/v1/enterprise/integrations",
        json={"name": "Broken", "provider": "x", "kind": "webhook", "config": {}},
        headers=headers,
    )
    assert invalid.status_code == 400

    tested = await client.post(
        f"/api/v1/enterprise/integrations/{connection_id}/test", headers=headers
    )
    assert tested.status_code == 200 and tested.json()["status"] == "active"

    synced = await client.post(
        f"/api/v1/enterprise/integrations/{connection_id}/sync", headers=headers
    )
    assert synced.status_code == 200
    assert synced.json()["last_sync_at"] is not None

    connections = (await client.get("/api/v1/enterprise/integrations", headers=headers)).json()
    assert len(connections) == 1

    removed = await client.delete(
        f"/api/v1/enterprise/integrations/{connection_id}", headers=headers
    )
    assert removed.status_code == 204


# ------------------------------------------------------ monitoring & observability


async def test_monitoring_health_metrics_and_alerts(client):
    org = await register_org(client, email="p15mon@test.co")
    headers = org["headers"]

    for name, value in [("uptime_percent", 99.9), ("latency_ms", 120.0)]:
        ingested = await client.post(
            "/api/v1/enterprise/monitoring/metrics",
            json={"name": name, "value": value, "unit": "ms" if name == "latency_ms" else "%"},
            headers=headers,
        )
        assert ingested.status_code == 201, ingested.text

    healthy = (await client.get("/api/v1/enterprise/monitoring/health", headers=headers)).json()
    assert healthy["status"] == "healthy"

    await client.post(
        "/api/v1/enterprise/monitoring/metrics",
        json={"name": "http_error_rate", "value": 30.0, "unit": "%"},
        headers=headers,
    )
    critical = (await client.get("/api/v1/enterprise/monitoring/health", headers=headers)).json()
    assert critical["status"] == "critical"

    alerts = (await client.get("/api/v1/enterprise/monitoring/alerts", headers=headers)).json()
    assert any(a["severity"] == "critical" and a["name"] == "http_error_rate" for a in alerts)

    metrics = (await client.get("/api/v1/enterprise/monitoring/metrics", headers=headers)).json()
    assert len(metrics) == 3


async def test_observability_logs_and_traces(client):
    org = await register_org(client, email="p15obs@test.co")
    headers = org["headers"]

    for i in range(3):
        ingested = await client.post(
            "/api/v1/enterprise/observability/logs",
            json={"message": f"checkpoint {i}", "level": "info", "source": "backup",
                  "trace_id": "trace-abc", "span_id": f"span-{i}"},
            headers=headers,
        )
        assert ingested.status_code == 201, ingested.text

    error = await client.post(
        "/api/v1/enterprise/observability/logs",
        json={"message": "checkpoint crashed", "level": "error", "source": "backup"},
        headers=headers,
    )
    assert error.status_code == 201

    logs = (await client.get("/api/v1/enterprise/observability/logs", headers=headers)).json()
    assert len(logs) == 4

    filtered = (await client.get(
        "/api/v1/enterprise/observability/logs?level=error", headers=headers
    )).json()
    assert len(filtered) == 1 and filtered[0]["level"] == "error"

    searched = (await client.get(
        "/api/v1/enterprise/observability/logs?search=crashed", headers=headers
    )).json()
    assert len(searched) == 1

    trace = (await client.get(
        "/api/v1/enterprise/observability/traces/trace-abc", headers=headers
    )).json()
    assert len(trace) == 3
    assert all(line["trace_id"] == "trace-abc" for line in trace)

    isolated = (await client.get(
        "/api/v1/enterprise/observability/logs", headers=(await register_org(
            client, email="p15obs2@test.co")).get("headers")
    )).json()
    assert isolated == []


# -------------------------------------------------------------------- security


async def test_security_brute_force_detection_and_resolution(client):
    org = await register_org(client, email="p15sec@test.co")
    headers = org["headers"]

    results = []
    for i in range(6):
        response = await client.post(
            "/api/v1/enterprise/security/detect/failed-login",
            json={"email": "ada@test.co", "source_ip": "203.0.113.77"},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        results.append(response.json())

    assert results[-1]["brute_force"] is True
    assert results[-1]["failed_count"] >= 5

    events = (await client.get(
        "/api/v1/enterprise/security/events?severity=high", headers=headers
    )).json()
    brute_force = [e for e in events if e["event_type"] == "brute_force.detected"]
    assert len(brute_force) == 1

    resolved = await client.post(
        f"/api/v1/enterprise/security/events/{brute_force[0]['id']}/resolve", headers=headers
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"

    rules = (await client.get("/api/v1/enterprise/security/rules", headers=headers)).json()
    assert rules["brute_force_threshold"] == 5


async def test_security_event_ingest_and_filters(client):
    org = await register_org(client, email="p15sec2@test.co")
    headers = org["headers"]

    event = await client.post(
        "/api/v1/enterprise/security/events",
        json={"event_type": "suspicious.activity", "severity": "medium",
              "title": "Odd login hour", "source_ip": "198.51.100.4",
              "details": {"hour": 3}},
        headers=headers,
    )
    assert event.status_code == 201, event.text

    events = (await client.get(
        "/api/v1/enterprise/security/events?status=open", headers=headers
    )).json()
    assert any(e["event_type"] == "suspicious.activity" for e in events)


# -------------------------------------------------------------------- compliance


async def test_compliance_controls_and_report(client):
    org = await register_org(client, email="p15comp@test.co")
    headers = org["headers"]

    frameworks = (await client.get(
        "/api/v1/enterprise/compliance/frameworks", headers=headers
    )).json()
    assert "iso27001" in frameworks and "soc2" in frameworks and "gdpr" in frameworks
    assert "hipaa" in frameworks and "pci" in frameworks and "fedramp" in frameworks

    for control, status in [("A.5.1", "pass"), ("A.6.1", "fail")]:
        response = await client.post(
            "/api/v1/enterprise/compliance/records",
            json={"framework": "iso27001", "control": control, "status": status,
                  "evidence": {"document": "sec-pol-1.pdf"}},
            headers=headers,
        )
        assert response.status_code == 201, response.text

    bad = await client.post(
        "/api/v1/enterprise/compliance/records",
        json={"framework": "nope", "control": "X", "status": "pass"},
        headers=headers,
    )
    assert bad.status_code == 400

    report = (await client.get("/api/v1/enterprise/compliance/report", headers=headers)).json()
    assert report["total_controls"] == 2
    assert report["passed"] == 1
    assert report["failed"] == 1
    assert report["readiness_percent"] == 50.0
    assert report["failed_controls"][0]["control"] == "A.6.1"

    record_id = report["failed_controls"][0]["control"]
    records = (await client.get(
        "/api/v1/enterprise/compliance/records?framework=iso27001", headers=headers
    )).json()
    rec = next(r for r in records if r["control"] == "A.6.1")
    updated = await client.patch(
        f"/api/v1/enterprise/compliance/records/{rec['id']}",
        json={"status": "pass"},
        headers=headers,
    )
    assert updated.status_code == 200 and updated.json()["status"] == "pass"


# ---------------------------------------------------------- licensing & features


async def test_licensing_and_entitlements(client):
    org = await register_org(client, email="p15lic@test.co")
    headers = org["headers"]

    license_row = (await client.get("/api/v1/enterprise/license", headers=headers)).json()
    assert license_row["plan"] == "starter"
    assert license_row["seats"] == 10

    refreshed = (await client.post("/api/v1/enterprise/license/refresh", headers=headers)).json()
    assert refreshed["seats_used"] >= 1

    upgraded = await client.patch(
        "/api/v1/enterprise/license", json={"plan": "enterprise"}, headers=headers
    )
    assert upgraded.status_code == 200, upgraded.text
    assert upgraded.json()["plan"] == "enterprise"
    assert "sso" in upgraded.json()["features"]
    assert "scim" in upgraded.json()["features"]

    bad = await client.patch(
        "/api/v1/enterprise/license", json={"plan": "platinum"}, headers=headers
    )
    assert bad.status_code == 400

    plans = (await client.get("/api/v1/enterprise/license/plans", headers=headers)).json()
    assert set(plans) == {"starter", "professional", "enterprise", "custom"}


async def test_feature_flag_targeting(client):
    org = await register_org(client, email="p15flag@test.co")
    headers = org["headers"]

    created = await client.post(
        "/api/v1/enterprise/feature-flags",
        json={"key": "beta.ai.copilot", "name": "AI Copilot", "enabled": True,
              "rules": {"percentage": 0}},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    flag_id = created.json()["id"]

    off = await client.post(
        "/api/v1/enterprise/feature-flags/evaluate",
        json={"key": "beta.ai.copilot"},
        headers=headers,
    )
    assert off.json()["enabled"] is False
    assert off.json()["reason"] == "percentage"

    updated = await client.patch(
        f"/api/v1/enterprise/feature-flags/{flag_id}",
        json={"rules": {"users": [org["user"]["id"]]}},
        headers=headers,
    )
    assert updated.status_code == 200

    on = await client.post(
        "/api/v1/enterprise/feature-flags/evaluate",
        json={"key": "beta.ai.copilot"},
        headers=headers,
    )
    assert on.json()["enabled"] is True
    assert on.json()["reason"] == "user_targeted"

    flags = (await client.get("/api/v1/enterprise/feature-flags", headers=headers)).json()
    assert len(flags) == 1

    deleted = await client.delete(f"/api/v1/enterprise/feature-flags/{flag_id}", headers=headers)
    assert deleted.status_code == 204


# -------------------------------------------------------------------- governed AI


async def test_ai_models_usage_and_consent(client, db_session_factory):
    org = await register_org(client, email="p15ai@test.co")
    headers = org["headers"]

    models = (await client.get("/api/v1/enterprise/ai/models", headers=headers)).json()
    assert any(m["model"] == "gpt-4o-mini" and m["available"] for m in models)
    assert any(m["model"] == "gpt-4o" and not m["available"] for m in models)

    usage = (await client.get("/api/v1/enterprise/ai/usage", headers=headers)).json()
    assert usage["requests"] == 0

    consent = await client.post(
        "/api/v1/enterprise/ai/consent",
        json={"scope": "memory_retention", "granted": True},
        headers=headers,
    )
    assert consent.status_code == 200 and consent.json()["granted"] is True

    bad_scope = await client.post(
        "/api/v1/enterprise/ai/consent",
        json={"scope": "everything", "granted": True},
        headers=headers,
    )
    assert bad_scope.status_code == 400

    async with db_session_factory() as db:
        from app.enterprise.ai_service import ai_service

        await ai_service.record_usage(
            db, organization_id=org["organization"]["id"], model="gpt-4o-mini", tokens=1234,
            actor_id=org["user"]["id"],
        )
        await db.commit()

    usage = (await client.get("/api/v1/enterprise/ai/usage", headers=headers)).json()
    assert usage["tokens_used"] == 1234 and usage["requests"] == 1


# ----------------------------------------------------- RBAC & tenant isolation


async def test_enterprise_rbac_and_multi_tenant_isolation(client):
    org = await register_org(client, email="p15rbac@test.co")
    headers = org["headers"]

    plugin = await _install_plugin(client, headers, plugin_key="rbac-plugin")
    await client.post(
        "/api/v1/enterprise/api-keys", json={"name": "Secret key"}, headers=headers
    )

    employee = await _invite_employee(client, headers, "p15emp@test.co", role="employee")
    emp_headers = employee["headers"]

    denied = await client.get("/api/v1/enterprise/admin/overview", headers=emp_headers)
    assert denied.status_code == 403
    denied = await client.get("/api/v1/enterprise/plugins", headers=emp_headers)
    assert denied.status_code == 403
    denied = await client.post(
        "/api/v1/enterprise/api-keys", json={"name": "Nope"}, headers=emp_headers
    )
    assert denied.status_code == 403

    # manager gets monitoring visibility but not administration
    manager = await _invite_employee(client, headers, "p15mgr@test.co", role="manager")
    mgr_headers = manager["headers"]
    health = await client.get("/api/v1/enterprise/monitoring/health", headers=mgr_headers)
    assert health.status_code == 200
    denied = await client.get("/api/v1/enterprise/admin/overview", headers=mgr_headers)
    assert denied.status_code == 403

    # tenant isolation: the employee org cannot see the owner org's data
    other = await register_org(client, email="p15rbac2@test.co")
    other_plugins = (await client.get("/api/v1/enterprise/plugins", headers=other["headers"])).json()
    assert other_plugins == []
    other_keys = (await client.get("/api/v1/enterprise/api-keys", headers=other["headers"])).json()
    assert other_keys == []

    overview = await client.get("/api/v1/enterprise/admin/overview", headers=headers)
    assert overview.status_code == 200
    body = overview.json()
    assert body["installed_plugins"] == 1
    assert body["active_api_keys"] == 1
    assert body["license"]["plan"] == "starter"


# ------------------------------------------------------------- events & search


async def test_enterprise_events_published(client):
    org = await register_org(client, email="p15events@test.co")
    headers = org["headers"]

    await _install_plugin(client, headers, plugin_key="event-plugin")
    key = await client.post(
        "/api/v1/enterprise/api-keys", json={"name": "Event key"}, headers=headers
    )
    key_id = key.json()["id"]
    await client.delete(f"/api/v1/enterprise/api-keys/{key_id}", headers=headers)
    await client.patch("/api/v1/enterprise/license", json={"plan": "enterprise"}, headers=headers)
    await client.post(
        "/api/v1/enterprise/security/events",
        json={"event_type": "policy.violation", "severity": "high", "title": "Violation"},
        headers=headers,
    )
    await client.post(
        "/api/v1/enterprise/compliance/records",
        json={"framework": "soc2", "control": "CC6.1", "status": "pass"},
        headers=headers,
    )

    names = await _event_names(client, headers)
    for expected in (
        "plugin.installed",
        "api.key.created",
        "api.key.revoked",
        "license.changed",
        "security.alert",
        "compliance.updated",
    ):
        assert expected in names, f"missing event {expected}"


async def test_enterprise_search(client):
    org = await register_org(client, email="p15search@test.co")
    headers = org["headers"]

    await _install_plugin(client, headers, plugin_key="findable-plugin")
    await client.post(
        "/api/v1/enterprise/feature-flags",
        json={"key": "beta.voice", "name": "Voice Reports", "enabled": True},
        headers=headers,
    )

    response = await client.get(
        "/api/v1/search?q=sentiment", headers=headers
    )
    assert response.status_code == 200, response.text
    types = {r["type"] for r in response.json()["results"]}
    assert "plugin" in types

    response = await client.get(
        "/api/v1/search?q=voice", headers=headers
    )
    types = {r["type"] for r in response.json()["results"]}
    assert "feature_flag" in types


# --------------------------------------------------------------- Phase 15 workers


async def test_phase15_workers_registered_and_run(db_session_factory):
    from app.workers.scheduler import WORKER_REGISTRY

    names = [name for name, _ in WORKER_REGISTRY]
    for expected in ("monitoring", "security", "compliance_policy", "sync", "plugin", "backup"):
        assert expected in names, f"worker {expected} not registered"

    from app.workers import (
        backup_worker,
        compliance_policy_worker,
        monitoring_worker,
        plugin_worker,
        security_worker,
        sync_worker,
    )

    async with db_session_factory() as db:
        assert isinstance(await monitoring_worker.run_once(db=db), int)
        assert isinstance(await security_worker.run_once(db=db), int)
        assert isinstance(await compliance_policy_worker.run_once(db=db), int)
        assert isinstance(await sync_worker.run_once(db=db), int)
        assert isinstance(await plugin_worker.run_once(db=db), int)
        assert isinstance(await backup_worker.run_once(db=db), int)
        await db.commit()
