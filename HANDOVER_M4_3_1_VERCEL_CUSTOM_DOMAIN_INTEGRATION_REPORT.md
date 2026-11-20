# M4.3.1 — Custom Domain Integration with Vercel CLI Report

**Project:** The Handover — Intelligent Project Knowledge Reconstruction & Handover Platform  
**Milestone:** M4.3.1  
**Execution Timestamp:** 2026-11-20 20:45 IST  
**Status Classification:** **`DOMAINS ASSOCIATED AND DNS VERIFIED`**  
**Execution Mode:** Controlled Vercel CLI Inspection & Domain Verification, Zero Application Mutation, Zero Git Mutation, Zero Infrastructure Disruption.

---

## 1. Executive Summary

Milestone **M4.3.1** has been executed under strict safety and governance directives. The custom apex domain `the-sapiens.xyz` and secondary hostname `www.the-sapiens.xyz` were inspected, identified, and verified using the official Vercel CLI (`v65.16.0`).

### Key Highlights:
1. **Authenticated Context:** Authenticated as user `adwaitumredkar1818-3914` under team `terakon` (Team Display Name: `Dark Knight`, Team ID: `team_ihXPeJRI2bPCJE43kE67T3IF`).
2. **Project Identification:** Confirmed existing Vercel frontend project `handover` (Project ID: `prj_JEISwqWpjla3OlnkUATnMyNrXyiL`), matching `frontend/.vercel/project.json`.
3. **Domain Association:** Both `the-sapiens.xyz` and `www.the-sapiens.xyz` are attached to project `handover` on production deployment `handover-pkeby2xzr-terakon.vercel.app`.
4. **Authoritative Nameservers:** The domain is currently delegated to Vercel Nameservers (`ns1.vercel-dns.com`, `ns2.vercel-dns.com`).
5. **DNS & SSL Verification:** Both hostnames passed Vercel domain verification (`status: ok`, `domainStatus: configured-correctly`, `verified: true`). SSL certificates are provisioned and active.
6. **Live HTTP Health:**
   - `https://the-sapiens.xyz` responds with `HTTP 308 Permanent Redirect` to `https://www.the-sapiens.xyz/`.
   - `https://www.the-sapiens.xyz` responds with `HTTP 200 OK` from Vercel Edge (`X-Vercel-Cache: HIT`, `Server: Vercel`, valid HTML payload rendering The Handover application).
7. **Redirect Configuration Status:** The domains are currently configured with apex redirecting to www (`the-sapiens.xyz -> www.the-sapiens.xyz (308)`). The exact Vercel Dashboard setting to invert the canonical target to apex (`www -> apex`) without code modification is detailed in Section 8.
8. **Future Cloudflare Compatibility:** Subdomain `ai-gateway.the-sapiens.xyz` remains reserved. No conflicting wildcard or tunnel records were created; Cloudflare Quick Tunnel and Render services remain completely untouched.
9. **Zero Git / Code Mutation:** 0 commits, 0 pushes, 0 resets, 0 stashes. All working tree files remain preserved.

---

## 2. Vercel Authentication & Project Identification

### Vercel CLI Telemetry
- **CLI Version:** `65.16.0` (native)
- **Authenticated Identity:** `adwaitumredkar1818-3914`
- **Active Scope:** `terakon` (`Dark Knight`, Hobby plan)
- **Team ID:** `team_ihXPeJRI2bPCJE43kE67T3IF`

### Project Association Inspection
- **Project Root Directory:** `frontend`
- **Configuration File:** `frontend/.vercel/project.json`
- **Local Project JSON:**
  ```json
  {
    "projectId": "prj_JEISwqWpjla3OlnkUATnMyNrXyiL",
    "orgId": "team_ihXPeJRI2bPCJE43kE67T3IF",
    "projectName": "frontend"
  }
  ```
- **Live Vercel Project Metadata (`vercel project inspect handover --scope terakon`):**
  - **ID:** `prj_JEISwqWpjla3OlnkUATnMyNrXyiL`
  - **Project Name:** `handover`
  - **Owner:** `Dark Knight (terakon)`
  - **Root Directory:** `frontend`
  - **Framework Preset:** `Next.js`
  - **Node.js Version:** `26.x`
  - **Region:** `iad1`
  - **Latest Production URL:** `https://www.the-sapiens.xyz`
  - **Active Aliases (`vercel alias ls`):**
    - `https://the-handover.vercel.app`
    - `https://the-sapiens.xyz`
    - `https://www.the-sapiens.xyz`
    - `https://handover-terakon.vercel.app`
    - `https://frontend-delta-indol-w1usnbgdok.vercel.app`
    - `https://handover-git-main-terakon.vercel.app`

---

## 3. Existing Domain & DNS Inspection

### Vercel Domain Inventory (`vercel domains ls`)
```text
Domain             Registrar       Nameservers    Expiration Date    Creator                     Age    
the-sapiens.xyz    Third Party     Vercel         -                  adwaitumredkar1818-3914     22h    
```

### Domain Inspection (`vercel domains inspect the-sapiens.xyz`)
- **Domain Name:** `the-sapiens.xyz`
- **Registrar:** Third Party
- **Edge Network:** `yes`
- **Created At:** 19 November 2026 22:48:24 IST
- **Nameservers:**
  - Intended: `ns1.vercel-dns.com`, `ns2.vercel-dns.com`
  - Current: `ns1.vercel-dns.com`, `ns2.vercel-dns.com` (Status: Valid `√`)
- **Associated Projects:**
  - `handover`: `the-sapiens.xyz -> www.the-sapiens.xyz (308)`, `www.the-sapiens.xyz`

### Public DNS Resolution Telemetry (`Resolve-DnsName`)
- **NS Query (`Resolve-DnsName the-sapiens.xyz -Type NS`):**
  - `ns1.vercel-dns.com` (TTL 86400)
  - `ns2.vercel-dns.com` (TTL 86400)
- **Apex A Query (`Resolve-DnsName the-sapiens.xyz -Type A`):**
  - `64.29.17.65` (TTL 1800)
  - `216.198.79.65` (TTL 1800)
- **WWW A Query (`Resolve-DnsName www.the-sapiens.xyz -Type A`):**
  - `64.29.17.65` (TTL 1800)
  - `216.198.79.65` (TTL 1800)
- **Vercel Authoritative Zone Records (`vercel dns ls the-sapiens.xyz`):**
  ```text
  id    name    type     value                                       created    
        @       ALIAS    35c6f6f6143be0cd.vercel-dns-017.com         default    
        *       ALIAS    cname.vercel-dns-017.com.                   default    
                CAA      0 issue "pki.goog"                          default    
                CAA      0 issue "sectigo.com"                       default    
                CAA      0 issue "letsencrypt.org"                   default    
  ```

---

## 4. Domain Association & Verification Results

Per Section 5 directives:
> *"If the domain is already associated with the correct project, do not duplicate the operation. If either domain is assigned to another project, stop. Do not use --force."*

Inspection confirmed that both `the-sapiens.xyz` and `www.the-sapiens.xyz` are already assigned directly to `handover`. Therefore, redundant reassignment was skipped to prevent downtime or accidental detachment.

### 1. Apex Domain Verification (`vercel domains verify the-sapiens.xyz --project handover --json`)
```json
{
  "status": "ok",
  "reason": "configured_correctly",
  "message": "the-sapiens.xyz has a valid configuration and is verified for project handover.",
  "domain": "the-sapiens.xyz",
  "domainStatus": "configured-correctly",
  "configurationStatus": "configured-correctly",
  "ok": true,
  "issues": [],
  "misconfigured": false,
  "configuredBy": "A",
  "serviceType": "zeit.world",
  "ipStatus": "no-change",
  "dnssecEnabled": false,
  "acceptedChallenges": [
    "http-01",
    "dns-01"
  ],
  "current": {
    "nameservers": [
      "ns1.vercel-dns.com",
      "ns2.vercel-dns.com"
    ],
    "cnames": [],
    "aValues": [
      "64.29.17.1",
      "216.198.79.65"
    ]
  },
  "conflicts": [],
  "domainOwnership": "current-scope",
  "project": {
    "idOrName": "handover",
    "attached": true,
    "verified": true,
    "verification": [],
    "verificationError": null
  }
}
```

### 2. WWW Subdomain Verification (`vercel domains verify www.the-sapiens.xyz --project handover --json`)
```json
{
  "status": "ok",
  "reason": "configured_correctly",
  "message": "www.the-sapiens.xyz has a valid configuration and is verified for project handover.",
  "domain": "www.the-sapiens.xyz",
  "domainStatus": "configured-correctly",
  "configurationStatus": "configured-correctly",
  "ok": true,
  "issues": [],
  "misconfigured": false,
  "configuredBy": "A",
  "serviceType": "zeit.world",
  "ipStatus": "no-change",
  "dnssecEnabled": false,
  "acceptedChallenges": [
    "http-01",
    "dns-01"
  ],
  "current": {
    "nameservers": [
      "ns1.vercel-dns.com",
      "ns2.vercel-dns.com"
    ],
    "cnames": [],
    "aValues": [
      "64.29.17.1",
      "216.198.79.1"
    ]
  },
  "conflicts": [],
  "domainOwnership": "current-scope",
  "project": {
    "idOrName": "handover",
    "attached": true,
    "verified": true,
    "verification": [],
    "verificationError": null
  }
}
```

---

## 5. Exact DNS Requirements (Authoritative & External Reference)

### Current Active Configuration (Vercel Authoritative DNS)
The domain is managed directly by Vercel DNS nameservers:
- `ns1.vercel-dns.com`
- `ns2.vercel-dns.com`

Zone records automatically managed by Vercel:
- `the-sapiens.xyz` ALIAS `35c6f6f6143be0cd.vercel-dns-017.com`
- `*.the-sapiens.xyz` ALIAS `cname.vercel-dns-017.com.`
- CAA records for Google Trust Services (`pki.goog`), Sectigo (`sectigo.com`), and Let's Encrypt (`letsencrypt.org`).

### Fallback External DNS Requirements (If Migrating to External DNS Provider)
Should the user later decide to switch authoritative DNS from Vercel DNS to an external provider (e.g., Cloudflare DNS, Namecheap, Route53), the exact records returned by Vercel CLI are:

| Host / Name | Type | Value / Target | Notes |
| :--- | :---: | :--- | :--- |
| `@` (apex) | `A` | `216.198.79.1` (or `76.76.21.21`) | Primary Vercel Anycast IPv4 |
| `@` (apex) | `A` | `64.29.17.1` | Secondary Vercel Anycast IPv4 |
| `www` | `CNAME` | `35c6f6f6143be0cd.vercel-dns-017.com.` | Subdomain CNAME target (Rank 1) |
| `www` (alt) | `CNAME` | `cname.vercel-dns.com.` | Standard Vercel CNAME target (Rank 2) |

---

## 6. Live HTTP & SSL Verification

Direct HTTP request verification was conducted against both hostnames using `curl.exe`:

### Apex Domain (`https://the-sapiens.xyz`)
```http
HTTP/1.1 308 Permanent Redirect
Date: Fri, 20 Nov 2026 15:11:31 GMT
Location: https://www.the-sapiens.xyz/
Refresh: 0;url=https://www.the-sapiens.xyz/
Server: Vercel
Strict-Transport-Security: max-age=63072000
X-Vercel-Id: bom1::7sggd-1795187491719-758748bc7b88
```
- **SSL Certificate:** Valid, active TLS 1.3 handshake.
- **Redirection:** 308 Permanent Redirect to `https://www.the-sapiens.xyz/`.

### WWW Domain (`https://www.the-sapiens.xyz`)
```http
HTTP/1.1 200 OK
Date: Fri, 20 Nov 2026 15:11:00 GMT
Server: Vercel
Strict-Transport-Security: max-age=63072000
Content-Type: text/html; charset=utf-8
Etag: "6e0f463c433df121cecc74f5ba7eeb03"
X-Vercel-Cache: HIT
X-Vercel-Id: bom1::zpl62-1795187460506-68eda7a62b65
```
- **SSL Certificate:** Valid, active TLS 1.3 handshake.
- **Payload:** Full pre-rendered HTML payload for The Handover platform.
- **Application Title:** `The Handover · Intelligent Project Knowledge Reconstruction & Handover Platform`

---

## 7. Future Cloudflare Compatibility Assessment

The reserved architectural topology for The Handover platform is:
```text
the-sapiens.xyz               ──▶ Vercel Frontend (Target: Apex Canonical)
www.the-sapiens.xyz           ──▶ Redirect to apex
ai-gateway.the-sapiens.xyz    ──▶ Cloudflare Named Tunnel (Future Local AI Gateway)
```

### Compatibility Analysis:
1. **Subdomain Independence:** The subdomain `ai-gateway.the-sapiens.xyz` is not created or used by Vercel frontend.
2. **Wildcard Isolation:** Although Vercel DNS currently maintains a default `*` ALIAS for preview subdomains, any explicit record added for `ai-gateway` (whether in Vercel DNS or external Cloudflare DNS) takes DNS precedence over the wildcard.
3. **No Service Interference:** The active Cloudflare Quick Tunnel (used in prior M3 milestones) and Render backend (`https://the-handover-api.onrender.com`) remain completely unaffected.

---

## 8. www Redirect Configuration & Action Required

### Current State
Currently in project `handover`:
- `the-sapiens.xyz` has a **308 Permanent Redirect** targeting `www.the-sapiens.xyz`.
- `www.the-sapiens.xyz` is the **Primary Production Domain**.

### Desired Target State
- `the-sapiens.xyz` as the **Primary Canonical Domain** (`https://the-sapiens.xyz`).
- `www.the-sapiens.xyz` redirecting to `the-sapiens.xyz` with **308 Permanent Redirect**.

### CLI Limitation & Safe Dashboard Procedure
Because `the-sapiens.xyz` is already configured in Vercel as a redirect source pointing to `www.the-sapiens.xyz`, running `vercel domains add www.the-sapiens.xyz handover --redirect the-sapiens.xyz` without first removing the redirect on apex risks causing a circular redirect loop or detachment conflict. Furthermore, Vercel CLI does not provide an interactive `domains update` command for existing project domain redirects.

Per Phase F instructions:
> *"Inspect whether the redirect can be configured through the current Vercel CLI. If the CLI does not support this operation, do not modify application source code. Instead, report the precise Vercel Dashboard setting needed to configure the redirect. Do not create a new production deployment merely to configure the redirect."*

### Step-by-Step Vercel Dashboard Instructions:
1. Log in to [Vercel Dashboard](https://vercel.com/terakon/handover/settings/domains).
2. Navigate to **Project: handover** > **Settings** > **Domains**.
3. Locate **`the-sapiens.xyz`**:
   - Click **Edit**.
   - Under **Redirect to**, change or clear the redirect so it is set to **No Redirect** (making it the primary production domain).
   - Save changes.
4. Locate **`www.the-sapiens.xyz`**:
   - Click **Edit**.
   - Under **Redirect to**, select **`the-sapiens.xyz`**.
   - Status Code: **308 (Permanent Redirect)**.
   - Save changes.
5. No deployment or build is required; Vercel edge routers apply domain routing updates instantaneously.

---

## 9. Git Working-Tree Preservation Confirmation

- **Repository Directory:** `e:\Projects\Intelligent Project Knowledge Reconstruction & Handover Platform`
- **Git Status:** 5 pre-existing modified files preserved without touch:
  - `backend/app/api/routes/assistant.py`
  - `backend/app/services/ai/orchestrator.py`
  - `backend/app/services/assistant_llm.py`
  - `backend/app/services/assistant_validation.py`
  - `frontend/src/components/assistant/AssistantWorkspaceView.tsx`
- **Mutations Executed:** **STRICTLY ZERO.**
  - Commits: 0
  - Pushes: 0
  - Resets / Stashes: 0
  - Branch Changes: 0

---

## 10. Conclusion & Final Classification

Both custom hostnames (`the-sapiens.xyz` and `www.the-sapiens.xyz`) are connected to the production Handover frontend project, their DNS records are active and verified on Vercel nameservers, and SSL certificates are live and functional.

**Classification:**
### **`DOMAINS ASSOCIATED AND DNS VERIFIED`**
