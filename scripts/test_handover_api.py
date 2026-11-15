import httpx

client = httpx.Client(base_url="http://127.0.0.1:8000/api/v1", timeout=60.0)

# 1. Login
login_res = client.post("/auth/login", json={
    "email": "shubham392007@gmail.com",
    "password": "Handover@2026!Sec"
})
print("Login status:", login_res.status_code)
assert login_res.status_code == 200, login_res.text
token = login_res.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

project_id = "ed33c53a-7678-4d5b-8212-64c233897142"

# 2. List cases
cases_res = client.get(f"/projects/{project_id}/handover/cases", headers=headers)
print("List cases status:", cases_res.status_code)
cases = cases_res.json()
print("Cases count:", cases["total"])

case_id = cases["items"][0]["id"]
print("Using case:", case_id)

# 3. Assemble package
asm_res = client.post(f"/projects/{project_id}/handover/cases/{case_id}/assemble", headers=headers, json={
    "assembly_notes": "Compiled from verified knowledge",
    "include_domains": [
        "decisions_rationale", "technical_architecture", "work_progress",
        "responsibilities_ownership", "dependencies_relationships",
        "bugs_blockers_risks", "operational_historical", "project_overview_context"
    ]
})
print("Assemble status:", asm_res.status_code)
if asm_res.status_code in (200, 201):
    version = asm_res.json()
    version_id = version["id"]
    print("Version assembled:", version_id, "v" + str(version["version_number"]))

    # 4. Assess readiness
    rd_res = client.post(f"/projects/{project_id}/handover/cases/{case_id}/readiness", headers=headers, json={
        "version_id": version_id,
        "notes": "Automated readiness evaluation"
    })
    print("Readiness status:", rd_res.status_code)
    if rd_res.status_code in (200, 201):
        rd = rd_res.json()
        print("Overall readiness:", rd["overall_score"], rd["overall_level"])

    # 5. Generate checklists
    chk_res = client.post(f"/projects/{project_id}/handover/cases/{case_id}/checklists/generate?version_id={version_id}", headers=headers)
    print("Checklists status:", chk_res.status_code)
    if chk_res.status_code in (200, 201):
        chks = chk_res.json()
        print("Checklists count:", len(chks))
        for c in chks:
            print(" -", c["checklist_type"], len(c["items"]), "items")

    # 6. Get case detail
    detail_res = client.get(f"/projects/{project_id}/handover/cases/{case_id}", headers=headers)
    print("Case detail status:", detail_res.status_code)
    if detail_res.status_code == 200:
        detail = detail_res.json()
        print("Status history count:", len(detail["status_history"]))
else:
    print("Assemble failed:", asm_res.text)
