#!/usr/bin/env python3
"""
Module Route Coverage Verification Script
"""

import os
import re
from pathlib import Path

BACKEND_MODULES = {
    "home": {"label": "Home", "route": "/home", "profiles": ["startup", "growing", "mid_market", "large_enterprise", "global_enterprise"]},
    "workspace": {"label": "Workspace", "route": "/workspace", "profiles": ["startup", "growing", "mid_market", "large_enterprise", "global_enterprise"]},
    "my-work": {"label": "My Work", "route": "/my-work", "profiles": ["startup", "growing", "mid_market", "large_enterprise", "global_enterprise"]},
    "my-day": {"label": "My Day", "route": "/my-work?tab=my-day", "profiles": ["startup", "growing", "mid_market", "large_enterprise", "global_enterprise"]},
    "company-home": {"label": "Company Home", "route": "/executive", "profiles": ["growing", "mid_market", "large_enterprise", "global_enterprise"]},
    "ai": {"label": "AI Companion", "route": "/ai", "profiles": ["startup", "growing", "mid_market", "large_enterprise", "global_enterprise"]},
    "company-brain": {"label": "Company Brain", "route": "/intelligence", "profiles": ["mid_market", "large_enterprise", "global_enterprise"]},
    "people": {"label": "People", "route": "/people", "profiles": ["growing", "mid_market", "large_enterprise", "global_enterprise"]},
    "departments": {"label": "Departments", "route": "/departments", "profiles": ["growing", "mid_market", "large_enterprise", "global_enterprise"]},
    "teams": {"label": "Teams", "route": "/teams", "profiles": ["growing", "mid_market", "large_enterprise", "global_enterprise"]},
    "projects": {"label": "Projects", "route": "/projects", "profiles": ["growing", "mid_market", "large_enterprise", "global_enterprise"]},
    "tasks": {"label": "Tasks", "route": "/tasks", "profiles": ["growing", "mid_market", "large_enterprise", "global_enterprise"]},
    "goals": {"label": "Goals", "route": "/goals", "profiles": ["growing", "mid_market", "large_enterprise", "global_enterprise"]},
    "approvals": {"label": "Approvals", "route": "/approvals", "profiles": ["growing", "mid_market", "large_enterprise", "global_enterprise"]},
    "risks": {"label": "Risks", "route": "/risks", "profiles": ["mid_market", "large_enterprise", "global_enterprise"]},
    "calendar": {"label": "Calendar", "route": "/calendar", "profiles": ["growing", "mid_market", "large_enterprise", "global_enterprise"]},
    "customers": {"label": "Customers", "route": "/customers", "profiles": ["growing", "mid_market", "large_enterprise", "global_enterprise"]},
    "finance": {"label": "Finance", "route": "/finance", "profiles": ["mid_market", "large_enterprise", "global_enterprise"]},
    "hr": {"label": "People Operations", "route": "/hr", "profiles": ["mid_market", "large_enterprise", "global_enterprise"]},
    "intelligence": {"label": "Background Intelligence", "route": "/intelligence", "profiles": ["large_enterprise", "global_enterprise"]},
    "twin": {"label": "Digital Twin", "route": "/twin", "profiles": ["large_enterprise", "global_enterprise"]},
    "knowledge": {"label": "Knowledge Hub", "route": "/knowledge", "profiles": ["growing", "mid_market", "large_enterprise", "global_enterprise"]},
    "governance": {"label": "Governance", "route": "/governance", "profiles": ["large_enterprise", "global_enterprise"]},
    "enterprise": {"label": "Enterprise Console", "route": "/enterprise", "profiles": ["large_enterprise", "global_enterprise"]},
    "developers": {"label": "Developer Portal", "route": "/developers", "profiles": ["mid_market", "large_enterprise", "global_enterprise"]},
    "learning": {"label": "Learning Center", "route": "/learning", "profiles": ["mid_market", "large_enterprise", "global_enterprise"]},
    "community": {"label": "Community", "route": "/communities", "profiles": ["startup", "growing", "mid_market", "large_enterprise", "global_enterprise"]},
    "search": {"label": "Universal Search", "route": "/search", "profiles": ["growing", "mid_market", "large_enterprise", "global_enterprise"]},
    "command": {"label": "Ask VCOS", "route": "/command-center", "profiles": ["growing", "mid_market", "large_enterprise", "global_enterprise"]},
    "admin": {"label": "Administration", "route": "/settings", "profiles": ["growing", "mid_market", "large_enterprise", "global_enterprise"]},
}

FRONTEND_ROUTES = {
    "ai": "/ai",
    "analytics": "/analytics",
    "announcements": "/announcements",
    "approvals": "/approvals",
    "board": "/board",
    "calendar": "/calendar",
    "capabilities": "/capabilities",
    "collaboration": "/collaboration",
    "command-center": "/command-center",
    "communities": "/communities",
    "customers": "/customers",
    "decisions": "/decisions",
    "departments": "/departments",
    "developers": "/developers",
    "documents": "/documents",
    "enterprise": "/enterprise",
    "events": "/events",
    "execution": "/execution",
    "executive": "/executive",
    "feed": "/feed",
    "finance": "/finance",
    "forums": "/forums",
    "games": "/games",
    "goals": "/goals",
    "governance": "/governance",
    "home": "/home",
    "hr": "/hr",
    "industry": "/industry",
    "innovation": "/innovation",
    "intelligence": "/intelligence",
    "knowledge": "/knowledge",
    "learning": "/learning",
    "meetings": "/meetings",
    "messages": "/messages",
    "my-work": "/my-work",
    "notifications": "/notifications",
    "onboarding": "/onboarding",
    "organization": "/organization",
    "ownership": "/ownership",
    "people": "/people",
    "people-decisions": "/people-decisions",
    "policies": "/policies",
    "polls": "/polls",
    "profile": "/profile",
    "projects": "/projects",
    "recognition": "/recognition",
    "recordings": "/recordings",
    "risks": "/risks",
    "rooms": "/rooms",
    "search": "/search",
    "settings": "/settings",
    "sops": "/sops",
    "tasks": "/tasks",
    "teams": "/teams",
    "templates": "/templates",
    "truth-center": "/truth-center",
    "twin": "/twin",
    "virtual-office": "/virtual-office",
    "wiki": "/wiki",
    "workspace": "/workspace",
}

def verify_coverage():
    print("=" * 80)
    print("MODULE ROUTE COVERAGE VERIFICATION")
    print("=" * 80)
    
    implemented_and_routed = []
    implemented_but_unrouted = []
    backend_only = []
    frontend_only = []
    
    for module_key, module_info in BACKEND_MODULES.items():
        route = module_info["route"]
        route_parts = route.strip("/").split("?")[0].split("/")
        route_dir = route_parts[0] if route_parts else ""
        
        full_path = Path(f"D:/vcos1/workspace/vcos/frontend/app/(app)/{route_dir}/page.tsx")
        if full_path.exists():
            implemented_and_routed.append((module_key, route))
        else:
            implemented_but_unrouted.append((module_key, route))
    
    backend_routes = set(m["route"] for m in BACKEND_MODULES.values())
    for route_name, route_path in FRONTEND_ROUTES.items():
        if route_path not in backend_routes:
            frontend_only.append((route_name, route_path))
    
    print(f"IMPLEMENTED AND ROUTED ({len(implemented_and_routed)}):")
    for module_key, route in sorted(implemented_and_routed):
        print(f"  {module_key:25s} -> {route}")
    
    print(f"\nIMPLEMENTED BUT UNROUTED ({len(implemented_but_unrouted)}):")
    for module_key, route in sorted(implemented_but_unrouted):
        print(f"  {module_key:25s} -> {route} (missing frontend route)")
    
    print(f"\nBACKEND ONLY ({len(backend_only)}):")
    for module_key, route in sorted(backend_only):
        print(f"  {module_key:25s} -> {route} (no frontend route defined)")
    
    print(f"\nFRONTEND ONLY ({len(frontend_only)}):")
    for route_name, route_path in sorted(frontend_only):
        print(f"  {route_name:25s} -> {route_path} (no backend module)")
    
    print("\nSUMMARY")
    print(f"Total Backend Modules: {len(BACKEND_MODULES)}")
    print(f"Total Frontend Routes: {len(FRONTEND_ROUTES)}")
    print(f"Fully Implemented: {len(implemented_and_routed)}")
    print(f"Missing Frontend Routes: {len(implemented_but_unrouted)}")
    print(f"Backend Only: {len(backend_only)}")
    print(f"Frontend Only: {len(frontend_only)}")
    print(f"Coverage: {len(implemented_and_routed)}/{len(BACKEND_MODULES)} = {len(implemented_and_routed)/len(BACKEND_MODULES)*100:.1f}%")
    
    return {
        "implemented_and_routed": implemented_and_routed,
        "implemented_but_unrouted": implemented_but_unrouted,
        "backend_only": backend_only,
        "frontend_only": frontend_only,
    }

if __name__ == "__main__":
    verify_coverage()
