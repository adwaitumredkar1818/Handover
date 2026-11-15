# Future Cloudflare Access & Cloudflare Tunnel Connectivity

## 1. Context and Architectural Goal

In the production deployment target:
- **FastAPI Backend** runs on **Render** (Cloud).
- **Local Inference Gateway** runs on a **Windows 11 Laptop** with RTX 4050 (Local).
- Direct inbound access to the local machine from the internet is **impossible and forbidden** (NAT, dynamic IP, security risks).

The solution is an outbound-only connection managed by **Cloudflare Tunnel (`cloudflared`)** protected by **Cloudflare Access** Service Tokens.

---

## 2. Target Production Architecture

```text
[Render FastAPI Backend]
          │
          │ HTTPS Request with:
          │ - CF-Access-Client-Id: <ID>
          │ - CF-Access-Client-Secret: <SECRET>
          │ - Authorization: Bearer <GATEWAY_TOKEN>
          ▼
[Cloudflare Edge / Cloudflare Access Policy]
          │ (Validates Service Token)
          ▼
[Cloudflare Tunnel (Outbound connection from Windows 11 host)]
          │
          ▼
[Local Inference Gateway (127.0.0.1:8002)]
          │ (Validates Bearer token & Tenant Scope)
          ▼
[Local Ollama / ChromaDB / Redis]
```

---

## 3. Configuration Requirements

### 3.1 Cloudflare Access Setup (Prerequisite for Future Phase)
1. In Cloudflare Zero Trust Dashboard, navigate to **Access** > **Service Auth**.
2. Create a Service Token named `the-handover-render-backend`.
3. Note the generated `Client ID` and `Client Secret`.
4. Create an Access Application for the tunnel hostname (e.g. `gateway-ai.yourdomain.com`).
5. Add an Access Policy allowing requests with the `the-handover-render-backend` Service Token.

### 3.2 Cloudflare Tunnel Setup (Windows Host)
1. Install `cloudflared` on Windows.
2. Authenticate and create a named tunnel:
   ```powershell
   cloudflared tunnel create handover-local-ai
   ```
3. Configure `config.yml`:
   ```yaml
   tunnel: <TUNNEL_ID>
   credentials-file: C:\Users\ASUS\.cloudflared\<TUNNEL_ID>.json

   ingress:
     - hostname: gateway-ai.yourdomain.com
       service: http://127.0.0.1:8002
     - service: http_status:404
   ```
4. Route DNS in Cloudflare:
   ```powershell
   cloudflared tunnel route dns handover-local-ai gateway-ai.yourdomain.com
   ```
5. Install and start `cloudflared` as a Windows Service:
   ```powershell
   cloudflared service install
   Start-Service cloudflared
   ```

### 3.3 Render Backend Environment Variables
Configure these in the Render Dashboard:

```env
INFERENCE_GATEWAY_ENABLED=true
INFERENCE_GATEWAY_BASE_URL=https://gateway-ai.yourdomain.com
INFERENCE_GATEWAY_TOKEN=<SHARED_32_BYTE_BEARER_TOKEN>
INFERENCE_GATEWAY_TIMEOUT_SECONDS=120.0

# Cloudflare Access Service Token Headers
CF_ACCESS_CLIENT_ID=<CLOUDFLARE_SERVICE_TOKEN_CLIENT_ID>
CF_ACCESS_CLIENT_SECRET=<CLOUDFLARE_SERVICE_TOKEN_CLIENT_SECRET>
```

---

## 4. End-to-End Security Guarantees

1. **Zero Open Inbound Ports**: The Windows 11 host accepts no incoming traffic from the internet. The tunnel only maintains outbound QUIC/HTTP2 connections to Cloudflare edge nodes.
2. **Double-Layered Authentication**:
   - Layer 1 (Cloudflare Edge): Requests must present valid `CF-Access-Client-Id` and `CF-Access-Client-Secret` matching the Zero Trust service token. Requests lacking these headers are rejected at the edge before reaching the local machine.
   - Layer 2 (Local Inference Gateway): Requests must present a valid `Authorization: Bearer <GATEWAY_TOKEN>` matching the local secret.
3. **Tenant Scoping**: All vector searches require mandatory `organisation_id` and `project_id`.
4. **Credential Isolation**: Client browsers never know the tunnel URL or service tokens. Only the Render backend possesses the gateway credentials.
