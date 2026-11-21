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

async def benchmark():
    access_token, raw_refresh, user_dict, org_dict, proj_dict = get_auth_token()
    print("Obtained fresh token for:", user_dict["email"])

    pages_to_test = [
        {"name": "Dashboard", "path": "/dashboard", "target_selector": "h1, [data-testid], button"},
        {"name": "Evidence Center", "path": "/evidence", "target_selector": "h1, [data-testid], button"},
        {"name": "Knowledge Intelligence", "path": "/knowledge", "target_selector": ".react-flow, h1, button"},
        {"name": "Relationship Explorer", "path": "/relationships", "target_selector": ".react-flow, h1, button"},
        {"name": "Team Members", "path": "/team", "target_selector": "table, h1, button"},
        {"name": "Verification Center", "path": "/verification", "target_selector": "table, h1, button"},
        {"name": "Handover Workspace", "path": "/handovers", "target_selector": "h1, button, table"},
    ]

    artifact_dir = r"C:\Users\verni\.gemini\antigravity\brain\59904699-9844-46f8-8624-2e360201eb1a"
    project_id = "cb6f2963-d674-4289-9f00-be6dcdb7fd21"
    org_id = "f37fb746-da77-4718-a9ab-54f864dd953e"

    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})

        await context.add_cookies([
            {
                "name": "handover_refresh_token",
                "value": raw_refresh,
                "domain": "localhost",
                "path": "/",
                "httpOnly": True,
                "secure": False,
                "sameSite": "Lax",
            }
        ])

        page = await context.new_page()

        # Seed local storage via initial dummy navigation
        await page.goto("http://localhost:3000/login", wait_until="commit")
        await page.evaluate(f"""() => {{
            localStorage.setItem('handover_access_token', '{access_token}');
            localStorage.setItem('handover_user', JSON.stringify({json.dumps(user_dict)}));
            localStorage.setItem('handover_active_org_id', '{org_id}');
            localStorage.setItem('handover_active_project_id', '{project_id}');
            localStorage.setItem('handover_cached_active_org', JSON.stringify({json.dumps(org_dict)}));
            localStorage.setItem('handover_cached_active_project', JSON.stringify({json.dumps(proj_dict)}));
        }}""")

        for item in pages_to_test:
            url = f"http://localhost:3000{item['path']}"
            print(f"\n==========================================")
            print(f"Testing {item['name']}: {url}")
            
            # Initial navigation
            t0 = time.perf_counter()
            await page.goto(url, wait_until="domcontentloaded")
            try:
                await page.wait_for_load_state("networkidle", timeout=12000)
            except Exception:
                pass
            nav_time = time.perf_counter() - t0
            print(f"  First Navigation Time: {nav_time:.2f}s")

            # Dedicated F5 Reload measurement
            t_reload_start = time.perf_counter()
            await page.reload(wait_until="domcontentloaded")
            try:
                await page.wait_for_load_state("networkidle", timeout=12000)
            except Exception:
                pass
            reload_time = time.perf_counter() - t_reload_start
            print(f"  F5 Reload Time (Network Idle): {reload_time:.2f}s")

            results.append({
                "page": item["name"],
                "path": item["path"],
                "initial_nav_s": round(nav_time, 2),
                "f5_reload_s": round(reload_time, 2),
            })

            # Capture special visual screenshots for graph pages
            if item["name"] == "Knowledge Intelligence":
                try:
                    arch_tab = page.locator("button:has-text('System Architecture')")
                    if await arch_tab.count() > 0:
                        await arch_tab.first.click()
                        await page.wait_for_timeout(2000)
                except Exception:
                    pass
                screenshot_path = os.path.join(artifact_dir, "verified_ki_system_architecture.png")
                await page.screenshot(path=screenshot_path)
                print(f"  Saved screenshot: {screenshot_path}")

            if item["name"] == "Relationship Explorer":
                await page.wait_for_timeout(2000)
                screenshot_path = os.path.join(artifact_dir, "verified_rel_people_contributions.png")
                await page.screenshot(path=screenshot_path)
                print(f"  Saved screenshot: {screenshot_path}")

        await browser.close()

    print("\n\n==========================================")
    print("FINAL SITE-WIDE BENCHMARK SUMMARY")
    print("==========================================")
    print(f"{'Page':<25} | {'Initial Nav':<12} | {'F5 Reload':<12}")
    print("-" * 55)
    for r in results:
        print(f"{r['page']:<25} | {r['initial_nav_s']:<11}s | {r['f5_reload_s']:<11}s")
    print("==========================================")

if __name__ == "__main__":
    asyncio.run(benchmark())
