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

async function verifyAll() {
  console.log("1. Authenticating to obtain access token...");
  const token = await getAccessToken();
  console.log("Access token obtained:", token.slice(0, 15) + "...");

  const port = 9556;
  const chromePath = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
  const userDataDir = path.join(process.env.TEMP || "C:\\Temp", `chrome_verify_${Date.now()}`);

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

  // Inject token and auth session into localStorage and cookie
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

  async function takeShot(name, delayMs = 3000) {
    await new Promise((r) => setTimeout(r, delayMs));
    const shotRes = await sendPage("Page.captureScreenshot", {
      format: "png",
      captureBeyondViewport: false,
    });
    const outPath = path.join(ARTIFACTS_DIR, name);
    fs.writeFileSync(outPath, Buffer.from(shotRes.result.data, "base64"));
    console.log(`Saved screenshot: ${name} (${Math.round(shotRes.result.data.length * 0.75 / 1024)} KB)`);
    return outPath;
  }

  // 1. Overview Page
  console.log("Navigating to /overview...");
  await sendPage("Page.navigate", { url: "http://localhost:3000/overview" });
  await takeShot("ui_01_top_nav_overview.png", 3500);

  // 2. Connected Sources Page
  console.log("Navigating to /sources...");
  await sendPage("Page.navigate", { url: "http://localhost:3000/sources" });
  await takeShot("ui_02_connected_sources.png", 3500);

  // 3. Open Slack Connect Modal via javascript evaluation
  console.log("Opening Slack Connect Modal...");
  await sendPage("Runtime.evaluate", {
    expression: `
      const buttons = Array.from(document.querySelectorAll('button'));
      const slackBtn = buttons.find(b => b.closest('.flex-col')?.textContent?.includes('Slack') && b.textContent.includes('Connect'));
      if (slackBtn) {
        slackBtn.click();
      } else {
        const anyConnect = buttons.find(b => b.textContent.includes('Connect'));
        if (anyConnect) anyConnect.click();
      }
    `,
  });
  await takeShot("ui_03_slack_connect_modal.png", 2000);

  // 4. Evidence Center Page
  console.log("Navigating to /evidence...");
  await sendPage("Page.navigate", { url: "http://localhost:3000/evidence" });
  await takeShot("ui_04_evidence_center_3_panels.png", 4000);

  // 5. Open Upload Document Modal
  console.log("Opening Upload Document Modal...");
  await sendPage("Runtime.evaluate", {
    expression: `
      const buttons = Array.from(document.querySelectorAll('button'));
      const uploadBtn = buttons.find(b => b.textContent.includes('Upload document') || b.textContent.includes('Upload'));
      if (uploadBtn) uploadBtn.click();
    `,
  });
  await takeShot("ui_05_upload_document_modal.png", 2000);

  // 6. Select Project Document category to see 14 subtypes
  console.log("Selecting project_document category...");
  await sendPage("Runtime.evaluate", {
    expression: `
      const catSelect = document.querySelector('select');
      if (catSelect) {
        catSelect.value = 'project_document';
        catSelect.dispatchEvent(new Event('change', { bubbles: true }));
      }
    `,
  });
  await takeShot("ui_06_upload_document_subtypes.png", 1500);

  // Close modal and click an item in Evidence Library
  console.log("Closing modal and inspecting evidence item tabs...");
  await sendPage("Runtime.evaluate", {
    expression: `
      const closeBtn = document.querySelector('button[aria-label="Close"], button:has(svg.lucide-x)');
      if (closeBtn) closeBtn.click();
      const esc = new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', keyCode: 27, which: 27, bubbles: true });
      document.dispatchEvent(esc);
    `,
  });
  await new Promise((r) => setTimeout(r, 1000));

  // Click on first evidence item in panel B if available
  await sendPage("Runtime.evaluate", {
    expression: `
      const item = document.querySelector('[data-evidence-item], button.w-full.text-left, div[class*="cursor-pointer"]');
      if (item) item.click();
    `,
  });
  await takeShot("ui_07_evidence_details_tabs.png", 2000);

  pageWs.close();
  ws.close();
  chrome.kill();
  try {
    fs.rmSync(userDataDir, { recursive: true, force: true });
  } catch {}
  console.log("Verification completed successfully!");
}

verifyAll().catch((err) => {
  console.error("Verification failed:", err);
  process.exit(1);
});
