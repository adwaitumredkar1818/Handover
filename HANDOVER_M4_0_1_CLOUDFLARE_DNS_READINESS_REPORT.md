# HANDOVER — M4.0.1 CLOUDFLARE ACCOUNT, DOMAIN & DNS READINESS REPORT

**Project:** The Handover — Intelligent Project Knowledge Reconstruction & Handover Platform  
**Milestone:** M4.0 — Cloud Connectivity Readiness Assessment  
**Phase:** M4.0.1 — Cloudflare Account, Domain & DNS Readiness  
**Timestamp:** 2026-11-15T03:51:00+05:30  
**Audit Mode:** Strictly Read-Only  
**Status:** Verification Completed  

---

## 1. Executive Summary

Phase **M4.0.1** conducts a strictly read-only audit of prerequisites for a future Cloudflare Tunnel connection bridging the future remote FastAPI backend (on Render) to the local Inference Gateway (running on Windows with an RTX 4050 6GB GPU).

### Key Audit Findings:
1. **Zero Active Tunneling Infrastructure**:
   - `cloudflared` CLI is **not installed** on the host (`Get-Command cloudflared` exited 1).
   - No `~/.cloudflared` credential or configuration directory exists.
   - No Windows service for `cloudflared` is registered or running.
   - Port `8002` remains strictly bound to loopback `127.0.0.1` and is currently closed/released.
2. **Account and Domain Status (Fact vs. Assumption)**:
   - **No local Cloudflare credentials or API keys** exist in environment variables, `.env`, or configuration files.
   - In accordance with the strict safety rules (no CLI authentication, no browser login scraping, no fabricated assumptions), **Cloudflare account ownership, active zones, nameservers, and domain names must be confirmed directly with the user**.
   - No owned domain has been declared in local configuration; `CF_ACCESS_ALLOWED_HOST`, `CF_ACCESS_CLIENT_ID`, and `CF_ACCESS_CLIENT_SECRET` remain blank in `.env.example`.
3. **Architecture and Capability Feasibility**:
   - Cloudflare Zero Trust (Free plan tier) supports up to 50 users and provides Cloudflare Tunnels (formerly Argo Tunnel), Access Applications, and Service Tokens at zero monetary cost.
   - The proposed hostname pattern `gateway-ai.<owned-domain>` is technically standard, feasible, and supported by Cloudflare Tunnel DNS routing via CNAME to `<TUNNEL_ID>.cfargotunnel.com`.
   - The double-layer defense mechanism (Cloudflare Access Service Token + Gateway Bearer Authentication) designed in M3.2.2/M3.2.3 and implemented in `InferenceGatewayClient` is fully verified and ready to consume these credentials once provisioned.

---

## 2. Cloudflare Account Readiness

| Item | Status | Evidence / Verification Method | Notes |
| :--- | :--- | :--- | :--- |
| **Cloudflare CLI (`cloudflared`)** | **Not Installed** | `Get-Command cloudflared` -> Not Found | Must be installed in a future authorized phase |
| **CLI Authentication State** | **Unauthenticated** | `~/.cloudflared` directory absent | No stored certs or tunnel keys on local disk |
| **Account Access / User Login** | **Requires Confirmation** | No API tokens or global keys in local environment | Interactive confirmation required from user |
| **Zero Trust Availability** | **Requires Confirmation** | Free tier natively includes Access & Tunnels | Needs active Cloudflare account setup |
| **Service Tokens Capability** | **Supported by Platform** | Cloudflare Access feature (Free tier includes Service Auth) | Validated against Cloudflare official documentation |

*Assertion:* No fake accounts or credentials were simulated. Account access must be confirmed directly by the operator.

---

## 3. Domain and DNS Readiness

| Item | Status | Verification & Technical Details |
| :--- | :--- | :--- |
| **Owned Domain Presence** | **Pending User Declaration** | No domain configured in project environment. `COOKIE_DOMAIN` in `.env` is empty. |
| **DNS Zone Status** | **Pending Domain Selection** | Cannot query DNS zone without an identified registered apex domain. |
| **Nameserver Delegation** | **Pending Domain Selection** | Domain must use Cloudflare authoritative nameservers (`*.ns.cloudflare.com`) or partial (CNAME) setup. |
| **Proposed Hostname** | `gateway-ai.<owned-domain>` | Standard subdomain convention. Routing via Cloudflare Tunnel CNAME creates zero DNS conflicts. |
| **TLS / SSL Consideration** | Cloudflare Edge Universal SSL | Cloudflare provides automated edge TLS (`https://gateway-ai.<domain>`). The tunnel from local machine to Cloudflare Edge is encrypted over QUIC/HTTP2. |

*Safety Assertion:* No DNS changes were attempted or simulated.

---

## 4. Tunnel Architecture Readiness

```text
[Render Cloud Backend]
          │
          │ HTTPS Request
          │ Headers:
          │   - CF-Access-Client-Id: <SERVICE_TOKEN_CLIENT_ID>
          │   - CF-Access-Client-Secret: <SERVICE_TOKEN_CLIENT_SECRET>
          │   - Authorization: Bearer <GATEWAY_CRYPTO_TOKEN>
          ▼
[Cloudflare Edge / Zero Trust Access Policy]
          │ (Validates Service Token & enforces destination host)
          ▼
[Cloudflare Tunnel (Outbound QUIC/HTTP2 from Windows 11 host)]
          │ (Terminates at local cloudflared daemon)
          ▼
[Local Inference Gateway (127.0.0.1:8002)]
          │ (Validates Bearer token & enforces tenant isolation)
          ▼
[Local Ollama (11434) / ChromaDB (8001) / Redis (6379)]
```

### Architectural Guardrails Verified:
1. **Outbound-Only Ingress**: The local Windows machine requires zero open inbound router ports, zero port-forwarding, and zero public IP exposure. The tunnel maintains persistent outbound connections to Cloudflare Edge.
2. **Two-Tier Authentication**:
   - **Tier 1 (Network / Perimeter)**: Cloudflare Access evaluates `CF-Access-Client-Id` and `CF-Access-Client-Secret`. Unauthorized requests are blocked at Cloudflare's edge before touching the tunnel.
   - **Tier 2 (Application / Tenant)**: Local Inference Gateway evaluates `Authorization: Bearer <token>` via constant-time HMAC and enforces tenant scope (`organisation_id`, `project_id`).
3. **Storage Decoupling**: Large documents and binary attachments are transferred via Supabase Storage, never through the inference tunnel. The tunnel handles lightweight inference requests (JSON completions, vector queries) only.
4. **Isolated Upstream Services**: Ollama, ChromaDB, and Redis remain bound strictly to `127.0.0.1` and are never routed directly through tunnel ingress rules.

---

## 5. Existing Environment Preservation

- **`cloudflared` Execution Check**: Confirmed uninstalled; zero running processes.
- **Port Audit**:
  - `127.0.0.1:8000`: Backend API (Local test process)
  - `127.0.0.1:8001`: ChromaDB (Docker)
  - `127.0.0.1:6379`: Redis (Docker)
  - `::1:11434`: Ollama (Local)
  - `127.0.0.1:8002`: Local Inference Gateway (Closed / Released)
  - External listeners: **Zero** (`0.0.0.0` bindings absent across all application services).
- **Git Working Tree**: Preserved without modifications, resets, cleans, or commits.
- **Database**: Zero migrations executed.

---

## 6. Security Risks & Prerequisites

### Security Risks Identified:
1. **Accidental Perimeter Bypass**: If an Access policy is misconfigured (e.g. set to "Allow Everyone" instead of "Service Token Only"), the gateway would be publicly exposed to internet scanners.
   - *Mitigation*: The local gateway's mandatory Bearer authentication and destination-validated `CF_ACCESS_ALLOWED_HOST` checks (implemented in M3.2.3) ensure it fails closed even if the perimeter policy is misconfigured.
2. **Host Machine Hibernation / Sleep**: If the Windows laptop sleeps, Render will receive 502/504 errors from Cloudflare.
   - *Mitigation*: Windows power settings must prevent sleep while serving as an active development inference node.

### Prerequisites for M4.0.2:
1. User provides or selects an active registered domain managed on Cloudflare.
2. User confirms Cloudflare Zero Trust account access.
3. Creation of an Access Service Token and Access Application in the Cloudflare Dashboard.
4. Download and setup of `cloudflared` on Windows.

---

## 7. Recommendation for Next Steps

Milestone **M4.0.1** is complete. No infrastructure changes have been executed.

**Recommendation:** Proceed to user consultation for:
- Confirmation of owned domain name on Cloudflare.
- Decision on Cloudflare Access setup workflow.

Awaiting review and approval.
