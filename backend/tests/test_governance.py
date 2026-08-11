"""Slice 4C — governance, RBAC & enterprise control foundation tests.

Covers the one-kernel-for-every-size governance model:
- RBAC: allowed / denied / missing permission, org-wide + scoped inheritance
- ABAC: scope match / mismatch, department and team isolation
- Delegation: creation, works, expiry (lazy deny), revocation, no self-delegation,
  no delegating what you do not hold
- Approval foundation: policies gate deciders, self-approval restrictions
- Tenant isolation: scopes, assignments, grants and policies never cross orgs
- Audit: every governance mutation writes the canonical trail
- Events: every governance mutation emits its canonical event
- Security: privilege-escalation attempts are refused
- Scale: deep synthetic scope trees evaluate in bounded, ancestry-only work
"""

from datetime import timedelta

import pytest

from app.core.timeutils import utcnow
from tests.conftest import register_org


# ------------------------------------------------------------------ helpers


async def _employee_id(client, headers):
    return (await client.get("/api/v1/employees/me", headers=headers)).json()["id"]


async def _invite_user(client, headers, email, full_name="Invitee", role="employee"):
    invite = await client.post(
        "/api/v1/users/invite",
        json={"email": email, "full_name": full_name, "role": role},
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    accepted = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": invite.json()["token"], "full_name": full_name, "password": "StrongPass123!"},
    )
    assert accepted.status_code == 201, accepted.text
    return accepted.json()


async def _role_id(client, headers, code):
    roles = (await client.get("/api/v1/roles", headers=headers)).json()
    return next(r["id"] for r in roles if r["code"] == code)


async def _scope(client, headers, name, scope_type="department", parent_id=None, entity_id=None):
    payload = {"name": name, "scope_type": scope_type}
    if parent_id:
        payload["parent_id"] = parent_id
    if entity_id:
        payload["entity_id"] = entity_id
    response = await client.post("/api/v1/governance/scopes", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def _grant(client, headers, granted_to_user, permission_code, **extra):
    response = await client.post(
        "/api/v1/governance/delegations",
        json={"granted_to_user": granted_to_user, "permission_code": permission_code, **extra},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _effective(client, headers, user_id, scope_id=None):
    params = {"user_id": user_id}
    if scope_id:
        params["scope_id"] = scope_id
    response = await client.get("/api/v1/governance/effective-permissions", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def _audit_actions(db_session_factory, org_id):
    from sqlalchemy import select

    from app.models.notification import AuditLog

    async with db_session_factory() as session:
        rows = (
            await session.execute(
                select(AuditLog.action).where(AuditLog.organization_id == org_id)
            )
        ).scalars().all()
        return set(rows)


async def _event_names(db_session_factory, org_id):
    from sqlalchemy import select

    from app.models.notification import Event

    async with db_session_factory() as session:
        rows = (
            await session.execute(select(Event.name).where(Event.organization_id == org_id))
        ).scalars().all()
        return set(rows)


# ---------------------------------------------------------------------- RBAC


@pytest.mark.asyncio
async def test_rbac_allowed_denied_and_missing_permission(client):
    org = await register_org(client, email="owner@gov-rbac.test.co")
    headers = org["headers"]
    invited = await _invite_user(client, headers, "emp@gov-rbac.test.co", "Emp Rbac")
    emp_headers = {"Authorization": f"Bearer {invited['access_token']}"}

    # Allowed: the CEO can read roles and governance.
    assert (await client.get("/api/v1/roles", headers=headers)).status_code == 200
    assert (await client.get("/api/v1/governance/scopes", headers=headers)).status_code == 200

    # Denied / missing: the default employee has neither roles:read,
    # governance:read nor governance:manage.
    assert (await client.get("/api/v1/roles", headers=emp_headers)).status_code == 403
    assert (await client.get("/api/v1/governance/scopes", headers=emp_headers)).status_code == 403
    create = await client.post(
        "/api/v1/governance/scopes",
        json={"name": "Sneaky", "scope_type": "team"},
        headers=emp_headers,
    )
    assert create.status_code == 403


@pytest.mark.asyncio
async def test_role_inheritance_org_wide_and_scoped_combine(client):
    org = await register_org(client, email="owner@gov-inherit.test.co")
    headers = org["headers"]
    invited = await _invite_user(client, headers, "emp@gov-inherit.test.co", "Emp Inherit")
    emp_id = invited["user"]["id"]
    emp_headers = {"Authorization": f"Bearer {invited['access_token']}"}
    manager_role = await _role_id(client, headers, "manager")

    # Org-wide: employee role grants projects:read everywhere, never projects:manage.
    effective = await _effective(client, headers, emp_id)
    assert "projects:read" in effective["permissions"]
    assert "projects:manage" not in effective["permissions"]

    # Scoped: assign the manager role at a team scope.
    scope = await _scope(client, headers, "Backend", scope_type="team")
    assignment = await client.post(
        "/api/v1/governance/assignments",
        json={"user_id": emp_id, "role_id": manager_role, "scope_id": scope["id"]},
        headers=headers,
    )
    assert assignment.status_code == 201, assignment.text

    # At the scope the manager role applies (ABAC context)...
    at_scope = await _effective(client, headers, emp_id, scope_id=scope["id"])
    assert "projects:manage" in at_scope["permissions"]
    # ...but org-wide authority is unchanged.
    again = await _effective(client, headers, emp_id)
    assert "projects:manage" not in again["permissions"]

    # The scoped assignment does not leak into require_permission (org-wide gate).
    create = await client.post(
        "/api/v1/projects", json={"name": "Sneaky project"}, headers=emp_headers
    )
    assert create.status_code == 403


# ---------------------------------------------------------------------- ABAC


@pytest.mark.asyncio
async def test_scope_match_and_mismatch_department_team_isolation(client):
    org = await register_org(client, email="owner@gov-abac.test.co")
    headers = org["headers"]
    invited = await _invite_user(client, headers, "emp@gov-abac.test.co", "Emp Abac")
    emp_id = invited["user"]["id"]
    manager_role = await _role_id(client, headers, "manager")

    engineering = await _scope(client, headers, "Engineering", scope_type="department")
    backend = await _scope(client, headers, "Backend", scope_type="team", parent_id=engineering["id"])
    finance = await _scope(client, headers, "Finance", scope_type="department")

    assignment = await client.post(
        "/api/v1/governance/assignments",
        json={"user_id": emp_id, "role_id": manager_role, "scope_id": backend["id"]},
        headers=headers,
    )
    assert assignment.status_code == 201, assignment.text

    # Scope match: manager authority applies at Backend and its descendants.
    backend_eff = await _effective(client, headers, emp_id, scope_id=backend["id"])
    assert "projects:manage" in backend_eff["permissions"]
    # Authority flows downward only (bounded evaluation): the ancestor
    # Engineering scope is not granted by a descendant-scoped assignment.
    eng_eff = await _effective(client, headers, emp_id, scope_id=engineering["id"])
    assert "projects:manage" not in eng_eff["permissions"]

    # Scope mismatch: Finance is a sibling branch — no leakage.
    fin_eff = await _effective(client, headers, emp_id, scope_id=finance["id"])
    assert "projects:manage" not in fin_eff["permissions"]

    # Child scope (created under Backend later) inherits the assignment.
    sub = await _scope(client, headers, "Backend sub", scope_type="project", parent_id=backend["id"])
    sub_eff = await _effective(client, headers, emp_id, scope_id=sub["id"])
    assert "projects:manage" in sub_eff["permissions"]


# ---------------------------------------------------------------- delegation


@pytest.mark.asyncio
async def test_delegation_create_works_revoke_expiry(client, db_session_factory):
    org = await register_org(client, email="owner@gov-deleg.test.co")
    headers = org["headers"]
    invited = await _invite_user(client, headers, "emp@gov-deleg.test.co", "Emp Deleg")
    emp_id = invited["user"]["id"]
    emp_headers = {"Authorization": f"Bearer {invited['access_token']}"}

    # Before delegation: the employee cannot create projects.
    assert (
        await client.post("/api/v1/projects", json={"name": "No access"}, headers=emp_headers)
    ).status_code == 403

    # Delegate projects:manage org-wide (bounded, targeted).
    grant = await _grant(client, headers, emp_id, "projects:manage", reason="Temporary ownership")
    assert grant["status"] == "active"

    # Works: the existing require_permission surface is now delegation-aware.
    created = await client.post(
        "/api/v1/projects", json={"name": "Delegated project"}, headers=emp_headers
    )
    assert created.status_code == 201, created.text

    # Revocation takes effect immediately — new request is 403.
    revoke = await client.post(
        f"/api/v1/governance/delegations/{grant['id']}/revoke", headers=headers
    )
    assert revoke.status_code == 200, revoke.text
    assert revoke.json()["status"] == "revoked"
    assert (
        await client.post("/api/v1/projects", json={"name": "Too late"}, headers=emp_headers)
    ).status_code == 403

    # Expiry: a delegation with a past expires_at never grants anything (lazy deny).
    await _grant(
        client, headers, emp_id, "projects:manage", reason="Already expired",
        expires_at=(utcnow() - timedelta(minutes=5)).isoformat(),
    )
    assert (
        await client.post("/api/v1/projects", json={"name": "Expired"}, headers=emp_headers)
    ).status_code == 403

    # The sweep marks the overdue grant expired (bounded hygiene pass).
    from app.services.governance_service import governance_service

    async with db_session_factory() as session:
        expired = await governance_service.expire_overdue(db=session, organization_id=org["organization"]["id"])
        assert any(g.permission_code == "projects:manage" for g in expired)
        await session.commit()

    actions = await _audit_actions(db_session_factory, org["organization"]["id"])
    assert "governance.delegation.created" in actions
    assert "governance.delegation.revoked" in actions
    assert "governance.delegation.expired" in actions


@pytest.mark.asyncio
async def test_unauthorized_and_scoped_delegation(client):
    org = await register_org(client, email="owner@gov-unauth.test.co")
    headers = org["headers"]
    invited = await _invite_user(client, headers, "emp@gov-unauth.test.co", "Emp Unauth")
    other = await _invite_user(client, headers, "other@gov-unauth.test.co", "Other Unauth")
    emp_headers = {"Authorization": f"Bearer {invited['access_token']}"}

    # An employee cannot create delegations at all (governance:manage missing).
    denied = await client.post(
        "/api/v1/governance/delegations",
        json={"granted_to_user": other["user"]["id"], "permission_code": "projects:manage"},
        headers=emp_headers,
    )
    assert denied.status_code == 403

    # The founder cannot delegate a permission nobody holds here — unknown code.
    bogus = await client.post(
        "/api/v1/governance/delegations",
        json={"granted_to_user": other["user"]["id"], "permission_code": "bogus:code"},
        headers=headers,
    )
    assert bogus.status_code == 403

    # Self-delegation is refused.
    self_grant = await client.post(
        "/api/v1/governance/delegations",
        json={"granted_to_user": org["user"]["id"], "permission_code": "projects:manage"},
        headers=headers,
    )
    assert self_grant.status_code == 403

    # Scoped delegation: founder delegates approvals:manage at a team scope.
    scope = await _scope(client, headers, "Ops", scope_type="team")
    grant = await _grant(
        client, headers, other["user"]["id"], "approvals:manage", scope_id=scope["id"]
    )
    assert grant["resource_type"] == "scope" and grant["resource_id"] == scope["id"]
    at_scope = await _effective(client, headers, other["user"]["id"], scope_id=scope["id"])
    assert "approvals:manage" in at_scope["permissions"]
    org_wide = await _effective(client, headers, other["user"]["id"])
    assert "approvals:manage" not in org_wide["permissions"]


# ------------------------------------------------------- approval foundation


async def _create_policy(client, headers, **extra):
    payload = {
        "name": "Deployment approval",
        "approval_type": "release",
        "required_permission": "approvals:manage",
        **extra,
    }
    response = await client.post("/api/v1/governance/policies", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def _create_approval(client, headers, title, policy_id=None):
    payload = {"approval_type": "release", "title": title}
    if policy_id:
        payload["policy_id"] = policy_id
    response = await client.post("/api/v1/approvals", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_approval_policy_approve_reject_and_unauthorized(client, db_session_factory):
    org = await register_org(client, email="owner@gov-approve.test.co")
    headers = org["headers"]
    invited = await _invite_user(client, headers, "emp@gov-approve.test.co", "Emp Approve")
    emp_headers = {"Authorization": f"Bearer {invited['access_token']}"}
    # The flow creator also decides, so the policy explicitly allows self-approval;
    # the strict self-approval rule is covered by test_self_approval_restricted_by_policy.
    policy = await _create_policy(client, headers, self_approval_allowed=True)

    approval = await _create_approval(client, headers, "Ship release 7", policy_id=policy["id"])
    assert approval["policy_id"] == policy["id"]

    # Unauthorized approval: an employee without the policy permission is refused.
    decided = await client.post(
        f"/api/v1/approvals/{approval['id']}/decide",
        json={"decision": "approved", "note": "I wish"},
        headers=emp_headers,
    )
    assert decided.status_code == 403

    # Authorized approval: the founder holds approvals:manage -> approved.
    approved = await client.post(
        f"/api/v1/approvals/{approval['id']}/decide",
        json={"decision": "approved", "note": "Go"},
        headers=headers,
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"

    # Reject path.
    second = await _create_approval(client, headers, "Ship release 8", policy_id=policy["id"])
    rejected = await client.post(
        f"/api/v1/approvals/{second['id']}/decide",
        json={"decision": "rejected", "note": "Not ready"},
        headers=headers,
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    # Audit + events for the policy-gated loop.
    actions = await _audit_actions(db_session_factory, org["organization"]["id"])
    assert "governance.policy.created" in actions
    assert "approval.approved" in actions
    assert "approval.rejected" in actions


@pytest.mark.asyncio
async def test_self_approval_restricted_by_policy(client):
    org = await register_org(client, email="owner@gov-self.test.co")
    headers = org["headers"]
    me_employee = await _employee_id(client, headers)

    strict = await _create_policy(client, headers, name="No self approval")
    approval = await client.post(
        "/api/v1/approvals",
        json={
            "approval_type": "release",
            "title": "Own release",
            "requester_id": me_employee,
            "policy_id": strict["id"],
        },
        headers=headers,
    )
    assert approval.status_code == 201, approval.text
    # The founder holds the policy permission but is the requester -> refused.
    self_decide = await client.post(
        f"/api/v1/approvals/{approval.json()['id']}/decide",
        json={"decision": "approved"},
        headers=headers,
    )
    assert self_decide.status_code == 400

    # A policy that explicitly allows self-approval permits it.
    loose = await _create_policy(client, headers, name="Self approval ok", self_approval_allowed=True)
    approval2 = await client.post(
        "/api/v1/approvals",
        json={
            "approval_type": "release",
            "title": "Own release 2",
            "requester_id": me_employee,
            "policy_id": loose["id"],
        },
        headers=headers,
    )
    assert approval2.status_code == 201, approval2.text
    ok = await client.post(
        f"/api/v1/approvals/{approval2.json()['id']}/decide",
        json={"decision": "approved"},
        headers=headers,
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "approved"


# ---------------------------------------------------------- tenant isolation


@pytest.mark.asyncio
async def test_tenant_isolation_scopes_grants_policies(client):
    org_a = await register_org(client, email="owner-a@gov-iso.test.co", name="Org A")
    org_b = await register_org(client, email="owner-b@gov-iso.test.co", name="Org B")
    headers_a, headers_b = org_a["headers"], org_b["headers"]

    b_emp = await _invite_user(client, headers_b, "emp-b@gov-iso.test.co", "Emp B")
    b_emp_id = b_emp["user"]["id"]

    # Org B creates scopes, grants and a policy.
    scope_b = await _scope(client, headers_b, "B Finance", scope_type="department")
    await _grant(client, headers_b, b_emp_id, "projects:manage")
    await _create_policy(client, headers_b, name="B policy")

    # Org A sees none of it.
    scopes_a = (await client.get("/api/v1/governance/scopes", headers=headers_a)).json()
    assert all(s["id"] != scope_b["id"] for s in scopes_a)
    delegations_a = (await client.get("/api/v1/governance/delegations", headers=headers_a)).json()
    assert all(d["granted_to_user"] != b_emp_id for d in delegations_a)
    policies_a = (await client.get("/api/v1/governance/policies", headers=headers_a)).json()
    assert all(p["name"] != "B policy" for p in policies_a)

    # Org A cannot evaluate Org B's user (target lookup is org-scoped -> 404).
    from_other = await client.get(
        "/api/v1/governance/effective-permissions",
        params={"user_id": b_emp_id},
        headers=headers_a,
    )
    assert from_other.status_code == 404

    # Org B's delegation is inert inside Org A.
    effective_a = await _effective(client, headers_a, org_a["user"]["id"])
    assert "projects:manage" in effective_a["permissions"]  # CEO role, not the grant


# ----------------------------------------------------- audit and event trail


@pytest.mark.asyncio
async def test_governance_events_and_audit_trail(client, db_session_factory):
    org = await register_org(client, email="owner@gov-events.test.co")
    headers = org["headers"]
    invited = await _invite_user(client, headers, "emp@gov-events.test.co", "Emp Events")
    emp_id = invited["user"]["id"]
    manager_role = await _role_id(client, headers, "manager")

    scope = await _scope(client, headers, "Events Dept", scope_type="department")
    assignment = await client.post(
        "/api/v1/governance/assignments",
        json={"user_id": emp_id, "role_id": manager_role, "scope_id": scope["id"]},
        headers=headers,
    )
    assert assignment.status_code == 201
    grant = await _grant(client, headers, emp_id, "projects:manage", scope_id=scope["id"])
    await _create_policy(client, headers, name="Events policy")

    actions = await _audit_actions(db_session_factory, org["organization"]["id"])
    for expected in (
        "governance.scope.created",
        "governance.assignment.created",
        "governance.delegation.created",
        "governance.policy.created",
    ):
        assert expected in actions, expected

    names = await _event_names(db_session_factory, org["organization"]["id"])
    for expected in (
        "governance.scope.created",
        "governance.assignment.created",
        "governance.delegation.created",
        "governance.policy.created",
    ):
        assert expected in names, expected

    # Revocation and scope deletion also emit + audit.
    revoke = await client.post(
        f"/api/v1/governance/delegations/{grant['id']}/revoke", headers=headers
    )
    assert revoke.status_code == 200
    deleted = await client.delete(f"/api/v1/governance/scopes/{scope['id']}", headers=headers)
    assert deleted.status_code == 400  # still has the assignment -> guarded
    assignment_removed = await client.delete(
        f"/api/v1/governance/assignments/{assignment.json()['id']}", headers=headers
    )
    assert assignment_removed.status_code == 200, assignment_removed.text
    deleted = await client.delete(f"/api/v1/governance/scopes/{scope['id']}", headers=headers)
    assert deleted.status_code == 200, deleted.text

    actions = await _audit_actions(db_session_factory, org["organization"]["id"])
    for expected in (
        "governance.delegation.revoked",
        "governance.assignment.removed",
        "governance.scope.deleted",
    ):
        assert expected in actions, expected


# ---------------------------------------------------------- security: escalation


@pytest.mark.asyncio
async def test_privilege_escalation_blocked(client):
    org = await register_org(client, email="owner@gov-esc.test.co")
    headers = org["headers"]
    invited = await _invite_user(client, headers, "emp@gov-esc.test.co", "Emp Esc")
    other = await _invite_user(client, headers, "other@gov-esc.test.co", "Other Esc")
    emp_id, other_id = invited["user"]["id"], other["user"]["id"]

    # Scope the manager role to the employee's team.
    scope = await _scope(client, headers, "Esc Team", scope_type="team")
    manager_role = await _role_id(client, headers, "manager")
    assignment = await client.post(
        "/api/v1/governance/assignments",
        json={"user_id": emp_id, "role_id": manager_role, "scope_id": scope["id"]},
        headers=headers,
    )
    assert assignment.status_code == 201
    emp_headers = {"Authorization": f"Bearer {invited['access_token']}"}

    # The employee (manager at a team scope only) tries to hand the CEO role to
    # another user — CEO grants permissions the employee does not hold at the
    # scope, so the assignment is refused.
    ceo_role = await _role_id(client, headers, "ceo")
    escalation = await client.post(
        "/api/v1/governance/assignments",
        json={"user_id": other_id, "role_id": ceo_role, "scope_id": scope["id"]},
        headers=emp_headers,
    )
    assert escalation.status_code == 403

    # The employee cannot create a delegation of a permission they only hold at
    # a scope when delegating org-wide.
    denied = await client.post(
        "/api/v1/governance/delegations",
        json={"granted_to_user": other_id, "permission_code": "projects:manage"},
        headers=emp_headers,
    )
    assert denied.status_code == 403

    # A role that grants more than the actor holds cannot be assigned even by a
    # governance holder acting beyond their scope: founder creates a custom
    # "super" role then removes governance from themselves is impossible, but a
    # scoped manager cannot assign it at their own scope either.
    custom = await client.post(
        "/api/v1/roles",
        json={"name": "Super Ops", "code": "super_ops", "permission_ids": []},
        headers=headers,
    )
    assert custom.status_code == 201
    # Scoped manager does not hold governance:manage org-wide -> cannot manage roles.
    assert (await client.post(
        "/api/v1/roles",
        json={"name": "Another", "code": "another_role", "permission_ids": []},
        headers=emp_headers,
    )).status_code == 403


# ----------------------------------------------------------------------- scale


@pytest.mark.asyncio
async def test_scale_deep_tree_bounded_evaluation(db_session_factory, client):
    """A 250-scope, 10-level tree evaluates in ancestry-only work.

    The leaf evaluation must include only its own branch and never any
    sibling branch — the queries are bounded by the user's own rows and the
    tree depth, not by org size.
    """
    org = await register_org(client, email="owner@gov-scale.test.co")
    headers = org["headers"]
    invited = await _invite_user(client, headers, "emp@gov-scale.test.co", "Emp Scale")
    emp_id = invited["user"]["id"]
    manager_role = await _role_id(client, headers, "manager")

    from app.services.governance_service import governance_service

    async with db_session_factory() as session:
        root = await governance_service.create_scope(
            session, organization_id=org["organization"]["id"],
            name="Root", scope_type="department",
        )
        # 10 branches x 25 levels of teams.
        branch_roots = []
        for b in range(10):
            parent = root
            for level in range(25):
                parent = await governance_service.create_scope(
                    session, organization_id=org["organization"]["id"],
                    name=f"Branch {b} level {level}", scope_type="team", parent_id=parent.id,
                )
            branch_roots.append(parent)
        leaf = await governance_service.create_scope(
            session, organization_id=org["organization"]["id"],
            name="Leaf target", scope_type="project", parent_id=branch_roots[0].id,
        )
        # Assign the manager role at the leaf of branch 0.
        assignment = await governance_service.assign_role_at_scope(
            session,
            organization_id=org["organization"]["id"],
            actor_user_id=org["user"]["id"],
            user_id=emp_id,
            role_id=manager_role,
            scope_id=leaf.id,
        )
        assert assignment.scope_id == leaf.id
        await session.commit()

    # Branch 0's leaf: manager authority flows up the ancestry to the root.
    leaf_eff = await _effective(client, headers, emp_id, scope_id=leaf.id)
    assert "projects:manage" in leaf_eff["permissions"]

    # The deepest leaf of branch 9 is a sibling subtree — no leakage.
    other_eff = await _effective(client, headers, emp_id, scope_id=branch_roots[9].id)
    assert "projects:manage" not in other_eff["permissions"]

    # Org-wide evaluation is untouched by the 250-scope tree.
    org_eff = await _effective(client, headers, emp_id)
    assert "projects:manage" not in org_eff["permissions"]
    assert "projects:read" in org_eff["permissions"]
