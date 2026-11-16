import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const ARTIFACTS_DIR = "C:\\Users\\Shubham\\.gemini\\antigravity\\brain\\f1e70b6b-09c5-4a12-819b-9553d61aef02";

async function getAccessToken() {
  const res = await fetch("http://localhost:8000/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email: "shubham392007@gmail.com",
      password: "Handover@2026!Sec",
    }),
  });
  if (!res.ok) {
    throw new Error(`Failed to log in: ${res.status} ${await res.text()}`);
  }
  const data = await res.json();
  return data.access_token;
}

async function verifyGitHubUI() {
  console.log("1. Authenticating to obtain access token...");
  const token = await getAccessToken();
  console.log("Access token obtained:", token.slice(0, 15) + "...");

  const port = 9559;
  const chromePath = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
  const userDataDir = path.join(process.env.TEMP || "C:\\Temp", `chrome_verify_gh_${Date.now()}`);

  console.log("2. Spawning Chrome with CDP on port", port);
  const chrome = spawn(chromePath, [
    "--headless=new",
    `--remote-debugging-port=${port}`,
    "--remote-allow-origins=*",
    `--user-data-dir=${userDataDir}`,
    "--disable-gpu",
    "--no-first-run",
    "--no-default-browser-check",
    "about:blank",
  ]);

  let wsUrl = null;
  for (let i = 0; i < 40; i++) {
    await new Promise((r) => setTimeout(r, 200));
    try {
      const res = await fetch(`http://127.0.0.1:${port}/json/version`);
      const data = await res.json();
      wsUrl = data.webSocketDebuggerUrl;
      if (wsUrl) break;
    } catch {}
  }

  if (!wsUrl) {
    chrome.kill();
    throw new Error(`Could not connect to Chrome debugging port on ${port}`);
  }

  const ws = new WebSocket(wsUrl);
  await new Promise((resolve) => ws.addEventListener("open", resolve));

  let id = 1;
  const callbacks = new Map();
  ws.addEventListener("message", (event) => {
    const msg = JSON.parse(event.data);
    if (msg.id && callbacks.has(msg.id)) {
      callbacks.get(msg.id)(msg);
      callbacks.delete(msg.id);
    }
  });

  function send(method, params = {}) {
    return new Promise((resolve) => {
      const msgId = id++;
      callbacks.set(msgId, resolve);
      ws.send(JSON.stringify({ id: msgId, method, params }));
    });
  }

  const targetRes = await send("Target.createTarget", { url: "about:blank" });
  const targetId = targetRes.result.targetId;

  const pageWs = new WebSocket(`ws://127.0.0.1:${port}/devtools/page/${targetId}`);
  await new Promise((resolve) => pageWs.addEventListener("open", resolve));

  let pageId = 1;
  const pageCallbacks = new Map();
  pageWs.addEventListener("message", (event) => {
    const msg = JSON.parse(event.data);
    if (msg.id && pageCallbacks.has(msg.id)) {
      pageCallbacks.get(msg.id)(msg);
      pageCallbacks.delete(msg.id);
    }
  });

  function sendPage(method, params = {}) {
    return new Promise((resolve) => {
      const msgId = pageId++;
      pageCallbacks.set(msgId, resolve);
      pageWs.send(JSON.stringify({ id: msgId, method, params }));
    });
  }

  await sendPage("Page.enable");
  await sendPage("DOM.enable");
  await sendPage("Runtime.enable");

  await sendPage("Page.addScriptToEvaluateOnNewDocument", {
    source: `
      try {
        localStorage.setItem("handover_access_token", "${token}");
        sessionStorage.setItem("handover_intro_seen", "1");
        document.cookie = "handover_access_token=${token}; path=/";
      } catch (e) {}
    `,
  });

  await sendPage("Emulation.setDeviceMetricsOverride", {
    width: 1440,
    height: 900,
    deviceScaleFactor: 2,
    mobile: false,
  });

  async function evalJs(expr) {
    const res = await sendPage("Runtime.evaluate", {
      expression: expr,
      returnByValue: true,
    });
    return res.result?.value;
  }

  async function takeShot(name, delayMs = 2500) {
    await new Promise((r) => setTimeout(r, delayMs));
    const title = (await evalJs("document.title")) || "";
    const modalHeader = (await evalJs("document.querySelector('h3, h2')?.textContent")) || "none";
    const modalText = (await evalJs("document.querySelector('.fixed')?.textContent?.slice(0, 100)")) || "no-modal";
    console.log(`[${name}] header='${modalHeader}', modalPreview='${modalText.replace(/\n/g, ' ')}'`);

    const shotRes = await sendPage("Page.captureScreenshot", {
      format: "png",
      captureBeyondViewport: false,
    });
    const outPath = path.join(ARTIFACTS_DIR, name);
    fs.writeFileSync(outPath, Buffer.from(shotRes.result.data, "base64"));
    console.log(`Saved screenshot: ${name} (${Math.round(shotRes.result.data.length * 0.75 / 1024)} KB)`);
    return outPath;
  }

  try {
    // 0. Initialize session on overview
    console.log("Navigating to /overview...");
    await sendPage("Page.navigate", { url: "http://localhost:3000/overview" });
    await new Promise((r) => setTimeout(r, 4000));

    // 1. Connected Sources Page showing GitHub card
    console.log("Navigating to /sources...");
    await sendPage("Page.navigate", { url: "http://localhost:3000/sources" });
    await takeShot("ui_github_01_sources_overview.png", 3500);

    // 2. Open GitHub Connect Modal
    console.log("Opening GitHub Connect Modal...");
    const openRes = await evalJs(`
      (() => {
        const buttons = Array.from(document.querySelectorAll('button'));
        const btn = buttons.find(b => b.textContent?.includes('Add repo') || (b.closest('.flex-col')?.textContent?.includes('GitHub') && b.textContent?.includes('Connect')));
        if (btn) { btn.click(); return 'clicked'; }
        return 'not-found';
      })()
    `);
    console.log("Modal opened result:", openRes);
    await new Promise((r) => setTimeout(r, 1500));

    // Expand Permissions Guide
    await evalJs(`
      if (typeof window.__setShowPermGuide === 'function') {
        window.__setShowPermGuide(true);
      }
    `);
    await takeShot("ui_github_02_modal_step1_pat.png", 2000);

    // 3. Step 2: Resource Discovery
    console.log("Transitioning to Step 2: Repository Discovery...");
    await evalJs(`
      if (typeof window.__setConnectModalStep === 'function') {
        window.__setConnectModalStep('select_resources', {
          account: 'shubham-dev',
          repos: [
            {
              external_resource_id: '789101',
              full_name: 'shubham-dev/skillpassport-core',
              name: 'skillpassport-core',
              owner_login: 'shubham-dev',
              description: 'Core microservices, authentication gateway and verifiable credential engine',
              is_private: true,
              default_branch: 'main',
              language: 'Python',
              topics: ['fastapi', 'credentials', 'security'],
              already_mapped: true,
              open_issues_count: 5
            },
            {
              external_resource_id: '789102',
              full_name: 'shubham-dev/skillpassport-frontend',
              name: 'skillpassport-frontend',
              owner_login: 'shubham-dev',
              description: 'Next.js 16 App Router interface for institutional onboarding and student profiles',
              is_private: true,
              default_branch: 'main',
              language: 'TypeScript',
              topics: ['nextjs', 'react', 'tailwind'],
              already_mapped: false,
              open_issues_count: 12
            },
            {
              external_resource_id: '789103',
              full_name: 'shubham-dev/evidence-pipeline-service',
              name: 'evidence-pipeline-service',
              owner_login: 'shubham-dev',
              description: 'Document extraction worker with GLM OCR and Nomic Embed Text integration',
              is_private: true,
              default_branch: 'main',
              language: 'Python',
              topics: ['ocr', 'rag', 'embeddings'],
              already_mapped: false,
              open_issues_count: 2
            },
            {
              external_resource_id: '789104',
              full_name: 'shubham-dev/public-docs-portal',
              name: 'public-docs-portal',
              owner_login: 'shubham-dev',
              description: 'Public documentation and API specifications site',
              is_private: false,
              default_branch: 'master',
              language: 'MDX',
              topics: ['docs'],
              already_mapped: false,
              open_issues_count: 0
            }
          ],
          selectedKeys: ['789102']
        });
      }
    `);
    await takeShot("ui_github_03_modal_step2_discovery.png", 2000);

    // 4. Step 3: Configure Scope
    console.log("Transitioning to Step 3: Granular Sync Scope...");
    // We can directly click "Configure Sync Scope" button!
    await evalJs(`
      const buttons = Array.from(document.querySelectorAll('button'));
      const scopeBtn = buttons.find(b => b.textContent?.includes('Configure Sync Scope'));
      if (scopeBtn) {
        scopeBtn.click();
      } else if (typeof window.__setConnectModalStep === 'function') {
        window.__setConnectModalStep('configure_scope');
      }
    `);
    await takeShot("ui_github_04_modal_step3_scope.png", 2000);

    // 5. Step 4: Review and Confirmation
    console.log("Transitioning to Step 4: Summary Review & Confirm...");
    // We can directly click "Review & Confirm" button!
    await evalJs(`
      const buttons = Array.from(document.querySelectorAll('button'));
      const confirmBtn = buttons.find(b => b.textContent?.includes('Review & Confirm'));
      if (confirmBtn) {
        confirmBtn.click();
      } else if (typeof window.__setConnectModalStep === 'function') {
        window.__setConnectModalStep('confirm');
      }
    `);
    await takeShot("ui_github_05_modal_step4_confirm.png", 2000);

    console.log("All GitHub screenshots captured successfully!");
  } finally {
    pageWs.close();
    ws.close();
    chrome.kill();
  }
}

verifyGitHubUI().catch((err) => {
  console.error("Verification failed:", err);
  process.exit(1);
});
