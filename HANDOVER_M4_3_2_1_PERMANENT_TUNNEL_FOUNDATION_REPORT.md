# M4.3.2.1 — Permanent Cloudflare Named Tunnel & Local AI Gateway Foundation Report

**Project:** The Handover — Intelligent Project Knowledge Reconstruction & Handover Platform  
**Milestone:** M4.3.2.1 — Permanent Cloudflare Named Tunnel & Local AI Gateway Foundation  
**Phase:** M4 — Production Infrastructure and Deployment  
**Execution Environment:** Windows 11 (PowerShell 5.1)  
**Target Hostname:** `ai-gateway.the-sapiens.xyz`  
**Target Origin:** `http://127.0.0.1:8002`  
**Execution Timestamp:** 2026-11-21 06:45 IST  
**Milestone Classification:** **`PERMANENT TUNNEL CREATED — DNS ACTIVATION PENDING`**  
**Execution Mode:** Controlled Infrastructure Implementation & Security Pre-flight Audit (Zero Git Mutations, Zero Credential Exposure)  

---

## 1. Executive Summary

Milestone **M4.3.2.1** has successfully replaced the temporary, randomized Cloudflare Quick Tunnel architecture with a persistent, production-grade **Cloudflare Named Tunnel** (`handover-ai-gateway`) bound to the stable hostname `ai-gateway.the-sapiens.xyz`.

### Key Milestone Achievements:
1. **Cloudflare Authentication Completed:** The user successfully authenticated the Cloudflare CLI via the official browser workflow. The origin certificate was securely generated and stored at `C:\Users\ASUS\.cloudflared\cert.pem` outside the Git repository.
2. **Permanent Named Tunnel Provisioned:** Created tunnel **`handover-ai-gateway`** with dedicated UUID **`9a34c722-2d50-41f1-8b80-05a04a625918`**.
3. **Ingress Configuration Validated:** Authored `C:\Users\ASUS\.cloudflared\config.yml` strictly routing `ai-gateway.the-sapiens.xyz` to `http://127.0.0.1:8002` with an HTTP 404 catch-all rule. The syntax was formally validated with `cloudflared tunnel ingress validate` returning `OK`.
4. **Cloudflare DNS Route Established:** Added CNAME record `ai-gateway.the-sapiens.xyz` &rarr; `9a34c722-2d50-41f1-8b80-05a04a625918.cfargotunnel.com` inside the Cloudflare zone.
5. **Vercel DNS CNAME Staged:** Added CNAME record `rec_ce675f7571223758223f4f03` for `ai-gateway` directly to Vercel DNS (`the-sapiens.xyz`).
6. **Live Named Tunnel Ingress Connected:** The permanent tunnel was launched and confirmed registered across 4 Cloudflare edge locations (`pnq01`, `bom11`, `bom10`) over QUIC protocol.
7. **Authoritative DNS Inventory Cataloged:** A comprehensive live audit of Vercel DNS was completed, documenting all Resend email DKIM/CNAME records, Vercel Apex ALIAS, and wildcard ALIAS records to guarantee zero email or frontend disruption.
8. **Windows Persistence Architecture Implemented:** Authored restart-resilient watchdog scripts:
   - `scripts/start_ai_gateway_persistent.ps1` (verifies backing services, starts gateway, polls `/health`, restarts on exit).
   - `scripts/start_named_tunnel_persistent.ps1` (waits for gateway readiness, executes named tunnel, auto-reconnects).
9. **Strict Safety Boundary Preserved:** Nameservers at the domain registrar remain untouched on Vercel DNS (`ns1.vercel-dns.com`, `ns2.vercel-dns.com`). No Render variables were changed. Zero git commits or secret leaks occurred.

---

## 2. Cloudflare Account & Zone Onboarding Status

- **Cloudflared Executable:** `C:\Program Files (x86)\cloudflared\cloudflared.exe`
- **Cloudflared Version:** `2026.11.0` (built `2026-11-12T03:21 UTC`)
- **CLI Authentication:** **VERIFIED** (`C:\Users\ASUS\.cloudflared\cert.pem` present).
- **Zone State:** `the-sapiens.xyz` added to user's Cloudflare account (Free Plan).
- **Assigned Cloudflare Nameservers:**
  - `tony.ns.cloudflare.com`
  - `zara.ns.cloudflare.com`
- **Current Live Nameservers:**
  - `ns1.vercel-dns.com`
  - `ns2.vercel-dns.com`
  *(Registrar nameservers remain on Vercel; nameserver migration pending approval in next milestone).*

---

## 3. Existing DNS Inventory (Authoritative Vercel DNS)

All existing live records were cataloged from Vercel DNS to ensure complete fidelity during future DNS migration:

| Record ID / Name | Type | Value / Destination | TTL | Purpose / Service | Criticality |
| :--- | :---: | :--- | :---: | :--- | :---: |
| `rec_ce675f75...`<br>`ai-gateway` | **CNAME** | `9a34c722-2d50-41f1-8b80-05a04a625918.cfargotunnel.com.` | 60 | **Cloudflare Named Tunnel Target** | **CRITICAL** (Local AI Ingress) |
| `rec_3b4fca5c...`<br>`resend._domainkey` | **TXT** | `p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCuFN5qvZp5RUEJGSAJNQFZTXJ7ZD9xFqkLJOiHYY2SGzwyyC3Wpb3+nhhRao25u+3w21AGxYivSBEO/iZJ6qQM0i6ZsQ0xFRE1mj9K3jZ1bC/6YsmqN83O91XzUPvE0rYIrISWHqUQp6Jl42M5AInEX7D+2/tTitvcwkmxRpWzZwIDAQAB` | 3600 | **Resend Email DKIM Signature** | **CRITICAL** (Email deliverability) |
| `rec_84641893...`<br>`rsend` | **CNAME** | `rsend-apne1.forge.rmta.net.` | 3600 | **Resend Return-Path / Mail Server** | **CRITICAL** (SPF / bounce handling) |
| `rec_f0505121...`<br>`send` | **CNAME** | `send.forge.rmta.net.` | 3600 | **Resend Mail Forwarding / Sending** | **CRITICAL** (Transactional outbound) |
| `@` (Apex) | **ALIAS** | `35c6f6f6143be0cd.vercel-dns-017.com`<br>*(Resolves to Anycast `64.29.17.65`, `216.198.79.65`)* | 1800 | **Vercel Production Frontend** | **CRITICAL** (Website Apex) |
| `*` (Wildcard) | **ALIAS** | `cname.vercel-dns-017.com.` | 1800 | **Vercel Frontend Subdomains**<br>*(Serves `www.the-sapiens.xyz`)* | **CRITICAL** (Website WWW redirect) |
| `@` (Apex) | **CAA** | `0 issue "pki.goog"` | Default | Google Trust Services SSL Authorization | High |
| `@` (Apex) | **CAA** | `0 issue "sectigo.com"` | Default | Sectigo SSL Authorization | High |
| `@` (Apex) | **CAA** | `0 issue "letsencrypt.org"` | Default | Let's Encrypt SSL Authorization | High |

---

## 4. Permanent Named Tunnel Specifications

- **Tunnel Name:** `handover-ai-gateway`
- **Tunnel UUID:** `9a34c722-2d50-41f1-8b80-05a04a625918`
- **Target Ingress Hostname:** `ai-gateway.the-sapiens.xyz`
- **Target Origin Service:** `http://127.0.0.1:8002`
- **Credentials File Location (Strictly Outside Repository):**
  `C:\Users\ASUS\.cloudflared\9a34c722-2d50-41f1-8b80-05a04a625918.json`
- **Filesystem Permissions:** Restrictive Windows NTFS ACLs (SYSTEM, Administrators, ASUS\Adwait only).
- **Creation Command Executed:**
  `cloudflared tunnel create handover-ai-gateway`
- **Active Edge Connections (QUIC):**
  - Connection 0: `ip=198.41.192.67 location=pnq01`
  - Connection 1: `ip=198.41.200.233 location=bom11`
  - Connection 2: `ip=198.41.192.77 location=pnq01`
  - Connection 3: `ip=198.41.200.13 location=bom10`

---

## 5. Tunnel Ingress Configuration (`config.yml`)

The configuration file was placed at `C:\Users\ASUS\.cloudflared\config.yml`:

```yaml
tunnel: 9a34c722-2d50-41f1-8b80-05a04a625918
credentials-file: C:\Users\ASUS\.cloudflared\9a34c722-2d50-41f1-8b80-05a04a625918.json

ingress:
  - hostname: ai-gateway.the-sapiens.xyz
    service: http://127.0.0.1:8002
    originRequest:
      connectTimeout: 30s
      noTLSVerify: false
      keepAliveTimeout: 120s
  - service: http_status:404
```

### Validation Result:
```text
PS > cloudflared tunnel --config "C:\Users\ASUS\.cloudflared\config.yml" ingress validate
Validating rules from C:\Users\ASUS\.cloudflared\config.yml
OK
```

---

## 6. DNS Route & Cloudflare Edge Discovery

### Architectural Insight:
1. When a Cloudflare Named Tunnel is routed, Cloudflare assigns target `<tunnel_id>.cfargotunnel.com`.
2. Cloudflare edge data centers proxy this hostname and terminate public TLS certificates **only when the zone's authoritative nameservers point to Cloudflare** (`tony.ns.cloudflare.com` / `zara.ns.cloudflare.com`).
3. Pointing a CNAME from external DNS (Vercel DNS) directly to `<tunnel_id>.cfargotunnel.com` resolves only internal Cloudflare overlay IPv6 addresses (`fd10:aec2:5dae::`), meaning public HTTP clients cannot connect until Cloudflare proxies the zone.
4. Therefore, full public traffic activation requires completing the registrar nameserver update to `tony.ns.cloudflare.com` and `zara.ns.cloudflare.com` in Milestone M4.3.2.2.

---

## 7. Windows Persistence Architecture

### A. Local AI Gateway Persistence (`scripts/start_ai_gateway_persistent.ps1`)
- **Ordering Enforcement:** Probes Ollama (`127.0.0.1:11434`) and ChromaDB (`127.0.0.1:8001`) before starting Uvicorn.
- **Execution:** Launches `.\backend\.venv\Scripts\python.exe -m uvicorn infrastructure.gateway.main:create_gateway_app --factory --host 127.0.0.1 --port 8002`.
- **Health Verification:** Verifies `http://127.0.0.1:8002/health` returns `HTTP 200 OK`.
- **Resilience:** Automatically restarts on unexpected process failure with backoff. Logs to `logs/ai_gateway_service.log` with zero token leakage.

### B. Cloudflare Named Tunnel Persistence (`scripts/start_named_tunnel_persistent.ps1`)
- **Ordering Enforcement:** Polls `http://127.0.0.1:8002/health` until the gateway responds before establishing the tunnel.
- **Execution:** Runs `cloudflared.exe tunnel --config C:\Users\ASUS\.cloudflared\config.yml run handover-ai-gateway`.
- **Resilience:** Auto-reconnects on transient network drops or process exit.
- **Windows Service Alternative:** If the user desires a background Windows Service running as `NT AUTHORITY\SYSTEM`, an Administrator PowerShell terminal can execute:
  ```powershell
  & "C:\Program Files (x86)\cloudflared\cloudflared.exe" service install
  ```

---

## 8. Security Review

| Dimension | Policy / Requirement | Verified Posture | Status |
| :--- | :--- | :--- | :---: |
| **Origin Binding** | Loopback only | Gateway strictly bound to `127.0.0.1:8002`. Rejects `0.0.0.0`. | **PASS** |
| **Ingress Scope** | Single hostname | Only `ai-gateway.the-sapiens.xyz` routed; 404 catch-all. | **PASS** |
| **Authentication** | Bearer token mandatory | Protected routes enforce constant-time `hmac.compare_digest`. | **PASS** |
| **Backing Services** | Zero external exposure | Ollama, ChromaDB, Redis, and PostgreSQL remain 100% loopback. | **PASS** |
| **Credential Storage**| Outside Git repository | Tunnel credentials in `C:\Users\ASUS\.cloudflared\`; zero secrets in repo. | **PASS** |
| **Filesystem ACLs** | Restrictive Windows ACLs | Only ASUS identity, SYSTEM, and Administrators have access. | **PASS** |
| **Secret Redaction** | Zero secret exposure | Tokens, private keys, and passwords excluded from logs/reports. | **PASS** |

---

## 9. Final Stop Condition Adherence

Per Section 13:
- **Registrar Nameservers:** UNCHANGED.
- **Render `INFERENCE_GATEWAY_BASE_URL`:** UNCHANGED.
- **Git Working Tree:** 0 commits, 0 pushes, 0 resets, 0 stashes.

---

## 10. Final Milestone Classification

The permanent named tunnel `handover-ai-gateway` is created, ingress configuration is validated, edge connections are live, and local persistence is established. Authoritative DNS activation is pending nameserver cutover at the domain registrar:

### **`PERMANENT TUNNEL CREATED — DNS ACTIVATION PENDING`**
