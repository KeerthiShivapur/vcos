import asyncio
import sys
import time

import httpx

API = "http://localhost:8999/api/v1"
PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        PASSED.append(name)
    else:
        FAILED.append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail and not ok else ""))


async def poll(client: httpx.AsyncClient, path: str, headers: dict, predicate, timeout: float = 60.0) -> object:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        r = await client.get(path, headers=headers)
        if r.status_code == 200:
            last = r.json()
            if predicate(last):
                return last
        await asyncio.sleep(2)
    return last


async def register(client: httpx.AsyncClient, name: str, slug: str, email: str, full_name: str):
    r = await client.post(
        f"{API}/auth/register",
        json={
            "organization_name": name,
            "organization_slug": slug,
            "industry": "Software",
            "country": "US",
            "timezone": "UTC",
            "currency": "USD",
            "full_name": full_name,
            "email": email,
            "username": email.split("@")[0],
            "password": "StrongPass123!",
        },
    )
    assert r.status_code == 201, r.text
    data = r.json()
    return {
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
        "access": data["access_token"],
        "user": data["user"],
        "organization": data["organization"],
    }


async def invite_and_accept(client: httpx.AsyncClient, headers: dict, email: str, full_name: str, role: str = "employee"):
    r = await client.post(f"{API}/users/invite", json={"email": email, "role": role, "full_name": full_name}, headers=headers)
    assert r.status_code == 201, r.text
    body = r.json()
    r2 = await client.post(
        f"{API}/auth/register/invite",
        json={"token": body["token"], "email": email, "full_name": full_name, "password": "StrongPass123!"},
    )
    assert r2.status_code == 201, r2.text
    return r2.json()


async def main() -> int:
    t = int(time.time() * 1000) % 10**8
    print("=== VCOS Slice 4B acceptance: messaging loop (live) ===")

    async with httpx.AsyncClient(base_url=API, timeout=30) as c:
        org = await register(c, "Message Corp", f"mc-{t}", f"ada{t}@mc.test.co", "Ada Founder")
        auth = org["headers"]
        bob = await invite_and_accept(c, auth, f"bob{t}@mc.test.co", "Bob Worker", "employee")
        bob_auth = {"Authorization": f"Bearer {bob['access_token']}"}
        employees = (await c.get(f"{API}/employees", headers=auth)).json()
        bob_id = next(e["id"] for e in employees if e["email"] == f"bob{t}@mc.test.co")
        print("1. Founder + Bob (employee, read-only messaging) set up")

        # --- DM + send -------------------------------------------------------
        dm = (
            await c.post(
                f"{API}/dms/{bob_id}",
                json={},
                headers=auth,
            )
        ).json()
        conv_id = dm["id"]
        check("DM conversation created with both members", dm["type"] == "dm" and dm["member_count"] == 2, str(dm)[:200])

        msg = (
            await c.post(
                f"{API}/conversations/{conv_id}/messages",
                json={"content": "The unicorn deployment is ready", "mentions": [bob_id]},
                headers=auth,
            )
        ).json()
        check("message sent with content + sender", msg["content"] == "The unicorn deployment is ready" and bool(msg["sender_id"]), str(msg)[:200])
        check("message carries mentions + reaction fields", "mentions" in msg and "reaction_count" in msg and "edited_at" in msg)
        check("Bob's unread_count is 1 for the new DM",
              any(x["id"] == conv_id and x["unread_count"] == 1 for x in (await c.get(f"{API}/conversations", headers=bob_auth)).json()),
              str([(x["id"][:8], x["unread_count"]) for x in (await c.get(f"{API}/conversations", headers=bob_auth)).json()]))
        print("2. DM created, message sent, unread surfaced to the recipient")

        # --- notifications via the event worker --------------------------------
        notif = await poll(
            c,
            f"{API}/notifications",
            bob_auth,
            lambda body: any(n["type"] == "mention" and "mentioned in a message" in n["title"] for n in body.get("items", [])),
        )
        check("Bob notified of the mention (event-worker delivered)",
              bool(notif) and any(n["type"] == "mention" for n in notif["items"]),
              str(notif)[:200])
        print("3. Mention notification delivered through the event loop")

        # --- edit / delete / reaction ------------------------------------------
        edited = (await c.patch(f"{API}/messages/{msg['id']}", json={"content": "The unicorn deployment is green"}, headers=auth)).json()
        check("message edited in place", edited["content"] == "The unicorn deployment is green" and edited["edited"] is True, str(edited)[:200])
        reacted = await c.post(f"{API}/messages/{msg['id']}/reactions", json={"emoji": "👍"}, headers=auth)
        check("reaction added (200)", reacted.status_code == 200 and reacted.json()["reaction_count"] == 1, reacted.text[:160])
        unreacted = await c.post(f"{API}/messages/{msg['id']}/reactions", json={"emoji": "👍"}, headers=auth)
        check("reaction toggle removes (count back to 0)", unreacted.json()["reaction_count"] == 0, unreacted.text[:160])
        deleted = await c.delete(f"{API}/messages/{msg['id']}", headers=auth)
        check("message soft-deleted (200)", deleted.status_code == 200 and "deleted" in deleted.text.lower(), deleted.text[:160])
        tombstone = (await c.get(f"{API}/conversations/{conv_id}/messages", headers=auth)).json()
        check("deleted message tombstones in the list", len(tombstone) == 1 and tombstone[0]["deleted"] is True, str(tombstone)[:200])
        print("4. Edit, reaction toggle and soft-delete coherent")

        # --- read receipts ------------------------------------------------------
        r2 = await c.post(f"{API}/conversations/{conv_id}/read", headers=bob_auth)
        check("Bob marks the conversation read (200)", r2.status_code == 200, r2.text[:160])
        convs = await c.get(f"{API}/conversations", headers=bob_auth)
        check("unread drops to 0 after reading",
              any(x["id"] == conv_id and x["unread_count"] == 0 for x in convs.json()),
              str([(x["id"][:8], x["unread_count"]) for x in convs.json()]))
        print("5. Read receipts close the unread loop")

        # --- RBAC: employee is read-only ----------------------------------------
        r403 = await c.post(f"{API}/conversations", json={"type": "channel", "title": "General"}, headers=bob_auth)
        check("employee cannot create a conversation (403)", r403.status_code == 403, r403.text[:160])
        r200 = await c.get(f"{API}/conversations", headers=bob_auth)
        check("employee can list conversations (200)", r200.status_code == 200, r200.text[:160])
        print("6. communication:write gates mutations")

        # --- universal search (member-scoped) ------------------------------------
        def hits(body) -> list:
            return body.get("results", [])

        search_msg = (
            await c.post(
                f"{API}/conversations/{conv_id}/messages",
                json={"content": "The unicorn roster ships next sprint"},
                headers=auth,
            )
        ).json()
        check("second message sent for search coverage", bool(search_msg.get("id")), str(search_msg)[:160])
        search_ada = (await c.get(f"{API}/search", params={"q": "unicorn"}, headers=auth)).json()
        hit_ada = [h for h in hits(search_ada) if h["type"] == "message"]
        check("founder finds the message via universal search", len(hit_ada) == 1 and hit_ada[0]["metadata"]["conversation_id"] == conv_id, str(search_ada)[:240])
        search_bob = (await c.get(f"{API}/search", params={"q": "unicorn"}, headers=bob_auth)).json()
        check("member finds the same message", any(h["type"] == "message" for h in hits(search_bob)), str(search_bob)[:240])
        print("7. Messages searchable within membership")

        # --- tenant isolation -----------------------------------------------------
        org_b = await register(c, "Sneaky Corp", f"sn-{t}", f"eve{t}@sn.test.co", "Eve Sneaky")
        headers_b = org_b["headers"]
        r404 = await c.get(f"{API}/conversations/{conv_id}", headers=headers_b)
        check("cross-org read of the conversation denied (404)", r404.status_code == 404, r404.text[:160])
        r404b = await c.get(f"{API}/conversations/{conv_id}/messages", headers=headers_b)
        check("cross-org read of messages denied (404)", r404b.status_code == 404, r404b.text[:160])
        search_b = (await c.get(f"{API}/search", params={"q": "unicorn"}, headers=headers_b)).json()
        check("outsider org sees no message hits", not any(h["type"] == "message" for h in hits(search_b)), str(search_b)[:240])
        print("8. Tenant isolation on messages + search")

        # --- the loop is audited and evented --------------------------------------
        events = (await c.get(f"{API}/events", headers=auth)).json()["items"]
        names = {e["name"] for e in events}
        for expected in (
            "messaging.conversation_created",
            "messaging.message_sent",
            "messaging.message_updated",
            "messaging.message_deleted",
            "messaging.message_reaction_added",
            "messaging.message_reaction_removed",
        ):
            check(f"event trail contains {expected}", expected in names, f"have: {sorted(names)[:12]}")
        audit = (await c.get(f"{API}/audit", params={"action": "messaging.message_sent", "resource_type": "message"}, headers=auth)).json()
        check("audit: messaging.message_sent recorded", audit.get("total", 0) >= 1, str(audit)[:200])
        audit_react = (await c.get(f"{API}/audit", params={"action": "messaging.message_reaction_added", "resource_type": "message"}, headers=auth)).json()
        check("audit: reaction add recorded", audit_react.get("total", 0) >= 1, str(audit_react)[:200])
        print("9. Audit + event trail complete for the messaging loop")

    print()
    print(f"RESULT: {len(PASSED)} passed, {len(FAILED)} failed")
    for name in FAILED:
        print(f"  FAILED: {name}")
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
