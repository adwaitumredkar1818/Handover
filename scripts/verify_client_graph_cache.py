import asyncio
import time
import json
import sys
import os
import uuid

sys.path.insert(0, os.path.abspath("backend"))

from app.core.config import get_settings
from app.db.session import create_db_engine, create_session_factory
from app.models import User
from app.models.organisation import Organisation
from app.models.project import Project
from app.core.security import utc_now, generate_refresh_token, hash_refresh_token, create_access_token
from app.repositories.auth import RefreshSessionRepository
from app.repositories.rbac import RbacRepository
from sqlalchemy import select
from playwright.async_api import async_playwright

def get_auth_token():
    settings = get_settings()
    engine = create_db_engine(settings)
    factory = create_session_factory(engine)
    session = factory()
    try:
        user = session.execute(select(User).where(User.email == "vernitg185@gmail.com")).scalar_one()
        now = utc_now()
        token_family_id = uuid.uuid4()
        raw_refresh_token = generate_refresh_token()
        token_hash = hash_refresh_token(raw_refresh_token)
        from datetime import timedelta
        expires_at = now + timedelta(days=settings.security.jwt_refresh_token_expire_days)
        
        RefreshSessionRepository(session).create(
            user_id=user.id,
            token_family_id=token_family_id,
            token_hash=token_hash,
            expires_at=expires_at,
            session_metadata={"user_agent": "playwright-bench", "ip": "127.0.0.1"},
        )
        access_token, expires_in = create_access_token(
            user_id=user.id,
            session_family_id=token_family_id,
            settings=settings,
            now=now,
        )
        session.commit()
        roles, permissions = RbacRepository(session).get_user_platform_roles_and_permissions(user.id)
        from app.services.auth import build_authenticated_user
        auth_user = build_authenticated_user(user, roles=roles, permissions=permissions)

        org = session.get(Organisation, uuid.UUID("f37fb746-da77-4718-a9ab-54f864dd953e"))
        proj = session.get(Project, uuid.UUID("cb6f2963-d674-4289-9f00-be6dcdb7fd21"))
        org_dict = {"id": str(org.id), "name": org.name, "slug": org.slug} if org else {}
        proj_dict = {"id": str(proj.id), "name": proj.name, "slug": proj.slug, "organisation_id": str(proj.organisation_id)} if proj else {}

        return access_token, raw_refresh_token, auth_user.model_dump(mode="json"), org_dict, proj_dict
    finally:
        session.close()

async def main():
    print("=" * 60)
    print("VERIFYING ZERO-RELOAD CLIENT-SIDE GRAPH CACHING")
    print("=" * 60)

    token, refresh_tok, user_dict, org_dict, proj_dict = get_auth_token()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        await context.add_cookies([
            {
                "name": "handover_refresh_token",
                "value": refresh_tok,
                "domain": "localhost",
                "path": "/",
                "httpOnly": True,
                "secure": False,
                "sameSite": "Lax",
            }
        ])

        page = await context.new_page()

        # Monitor all network requests
        network_requests = []
        def on_request(req):
            if "api/v1" in req.url:
                network_requests.append({"url": req.url, "method": req.method, "time": time.time()})
        page.on("request", on_request)

        # Seed localStorage
        await page.goto("http://localhost:3000/login", wait_until="commit")
        await page.evaluate(
            """({ token, user, org, project }) => {
                localStorage.setItem("handover_access_token", token);
                localStorage.setItem("handover_cached_user", JSON.stringify(user));
                localStorage.setItem("handover_cached_active_org", JSON.stringify(org));
                localStorage.setItem("handover_cached_active_project", JSON.stringify(project));
            }""",
            {"token": token, "user": user_dict, "org": org_dict, "project": proj_dict},
        )

        print("\n--- PHASE 1: Initial Cold Load of Knowledge Intelligence ---")
        t0 = time.time()
        await page.goto("http://localhost:3000/knowledge", wait_until="networkidle")
        await page.wait_for_selector(".react-flow__node", timeout=15000)
        cold_load_time = (time.time() - t0) * 1000
        print(f"Cold load of Technology Stack: {cold_load_time:.1f}ms")

        # Load System Architecture
        print("\n--- PHASE 2: Load System Architecture (First visit) ---")
        network_requests.clear()
        t0 = time.time()
        await page.click("button:has-text('System Architecture')")
        await page.wait_for_selector(".react-flow__node", timeout=15000)
        sys_arch_first = (time.time() - t0) * 1000
        reqs_sys_first = len([r for r in network_requests if "knowledge-intelligence/graph" in r["url"]])
        print(f"First visit System Architecture: {sys_arch_first:.1f}ms, API requests: {reqs_sys_first}")

        # Load Features & Workflows
        print("\n--- PHASE 3: Load Features & Workflows (First visit) ---")
        network_requests.clear()
        t0 = time.time()
        await page.click("button:has-text('Features & Workflows')")
        await page.wait_for_selector(".react-flow__node", timeout=15000)
        feat_first = (time.time() - t0) * 1000
        reqs_feat_first = len([r for r in network_requests if "knowledge-intelligence/graph" in r["url"]])
        print(f"First visit Features & Workflows: {feat_first:.1f}ms, API requests: {reqs_feat_first}")

        # Switch BACK to Technology Stack (Must be cached!)
        print("\n--- PHASE 4: Switch Back to Technology Stack (Cached Test) ---")
        network_requests.clear()
        t0 = time.time()
        await page.click("button:has-text('Technology Stack')")
        # Ensure nodes are present immediately
        await page.wait_for_selector(".react-flow__node", timeout=2000)
        t_switch_tech = (time.time() - t0) * 1000
        reqs_tech_cached = len([r for r in network_requests if "knowledge-intelligence/graph" in r["url"]])
        print(f"Cached switch to Technology Stack: {t_switch_tech:.1f}ms, API requests: {reqs_tech_cached}")
        assert reqs_tech_cached == 0, f"Expected 0 API requests for cached graph, got {reqs_tech_cached}"

        # Switch BACK to System Architecture (Must be cached!)
        print("\n--- PHASE 5: Switch Back to System Architecture (Cached Test) ---")
        network_requests.clear()
        t0 = time.time()
        await page.click("button:has-text('System Architecture')")
        await page.wait_for_selector(".react-flow__node", timeout=2000)
        t_switch_sys = (time.time() - t0) * 1000
        reqs_sys_cached = len([r for r in network_requests if "knowledge-intelligence/graph" in r["url"]])
        print(f"Cached switch to System Architecture: {t_switch_sys:.1f}ms, API requests: {reqs_sys_cached}")
        assert reqs_sys_cached == 0, f"Expected 0 API requests for cached graph, got {reqs_sys_cached}"

        # Navigate to Relationship Explorer
        print("\n--- PHASE 6: Navigate to Relationship Explorer ---")
        network_requests.clear()
        t0 = time.time()
        await page.goto("http://localhost:3000/relationships", wait_until="networkidle")
        await page.wait_for_selector(".react-flow__node", timeout=15000)
        t_rel_first = (time.time() - t0) * 1000
        reqs_rel_first = len([r for r in network_requests if "relationships" in r["url"]])
        print(f"First visit Relationship Explorer: {t_rel_first:.1f}ms, API requests: {reqs_rel_first}")

        # Switch to Work Clusters tab in Relationship Explorer
        print("\n--- PHASE 7: Switch to Work Clusters Tab ---")
        network_requests.clear()
        t0 = time.time()
        await page.click("button[role='tab']:has-text('Work Clusters')")
        await page.wait_for_timeout(500)
        t_clusters_first = (time.time() - t0) * 1000
        print(f"Work Clusters tab load: {t_clusters_first:.1f}ms")

        # Switch back to People & Contributions
        print("\n--- PHASE 8: Switch Back to People & Contributions ---")
        network_requests.clear()
        t0 = time.time()
        await page.click("button[role='tab']:has-text('People & Contributions')")
        await page.wait_for_selector(".react-flow__node", timeout=5000)
        t_rel_people_cached = (time.time() - t0) * 1000
        reqs_rel_people_cached = len([r for r in network_requests if "relationships/contributors/graph" in r["url"]])
        print(f"Cached switch to People & Contributions: {t_rel_people_cached:.1f}ms, API requests: {reqs_rel_people_cached}")
        assert reqs_rel_people_cached == 0, f"Expected 0 API requests for cached contributor graph, got {reqs_rel_people_cached}"

        # Cross-Page Navigation Back to Knowledge Intelligence (Testing SessionStorage Tier 2 cache)
        print("\n--- PHASE 9: Navigate back to Knowledge Intelligence (SessionStorage Tier 2) ---")
        network_requests.clear()
        t0 = time.time()
        await page.goto("http://localhost:3000/knowledge", wait_until="networkidle")
        await page.wait_for_selector(".react-flow__node", timeout=5000)
        t_ki_cross_page = (time.time() - t0) * 1000
        reqs_ki_cross_page = len([r for r in network_requests if "knowledge-intelligence/graph" in r["url"]])
        print(f"Cross-page nav to Knowledge Intelligence: {t_ki_cross_page:.1f}ms, API requests: {reqs_ki_cross_page}")
        assert reqs_ki_cross_page == 0, f"Expected 0 API requests because graph is persisted in sessionStorage, got {reqs_ki_cross_page}"

        # Test Refresh Button Cache Invalidation
        print("\n--- PHASE 10: Test Refresh Button Cache Invalidation ---")
        network_requests.clear()
        t0 = time.time()
        await page.click("button:has-text('Refresh')")
        await page.wait_for_timeout(800)
        reqs_refresh = len([r for r in network_requests if "knowledge-intelligence" in r["url"]])
        print(f"After clicking Refresh, API requests: {reqs_refresh} (properly re-fetched from server)")
        assert reqs_refresh > 0, "Expected cache to be invalidated on manual Refresh click!"

        print("\n" + "=" * 60)
        print("ALL ZERO-RELOAD CLIENT-SIDE GRAPH CACHING CHECKS PASSED!")
        print("=" * 60)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
