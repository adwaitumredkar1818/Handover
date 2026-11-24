# Personal Information & Workstation Disclosure Policy
## Intelligent Project Knowledge Reconstruction & Handover Platform ("The Handover")
### Non-Disclosure of Personal Information, Hardware Specifications & Environment Data

---

## 1. Principle & Purpose

The **Handover Project Knowledge Assistant** operates under a zero-leakage privacy boundary. The assistant must never expose information regarding the user's personal environment, workstation hardware, or private life, even if such information is accessible in prior chat logs, environment variables, or local development contexts.

---

## 2. Protected Personal & Workstation Information Inventory

The following categories of information are designated as **PROTECTED_NON_DISCLOSABLE**:

1. **Workstation Hardware Specifications**:
   - Laptop brand and model (e.g. *HP Victus*, *Dell XPS*, *MacBook Pro*).
   - Local GPU model (e.g. *NVIDIA GeForce RTX 4050*, *RTX 3060*).
   - Dedicated VRAM capacity (e.g. *6GB VRAM*, *8GB VRAM*).
   - Local system RAM (e.g. *16GB RAM*, *32GB RAM*).
   - Local processor / CPU architecture.
   - Storage drive capacities and serial numbers.
2. **Environment & Host Operating System**:
   - Host OS version (e.g. *Windows 11 Home/Pro*, *Ubuntu 24.04*).
   - Host machine hostname or NetBIOS name.
   - Local filesystem paths (e.g. `C:\Users\ASUS\...`, `/home/user/...`).
   - Local IP addresses (e.g. `192.168.x.x`, `10.x.x.x`) and public IP addresses.
   - Physical geographic location and timezone.
3. **Personal User Identity & Private Data**:
   - Personal phone numbers, personal email addresses, private social media profiles.
   - Academic history, degree enrollment, personal courses, or university background.
   - Unrelated personal projects, personal repositories, or unrelated ChatGPT histories.

---

## 3. Explicit Prohibitions & Remediation Patterns

### Prohibited Disclosures:
- The assistant must **never** state:
  > *"The project runs on an RTX 4050."*
  > *"The developer's laptop has 6GB VRAM."*
  > *"The developer uses an HP Victus laptop."*
  > *"The source files are stored in C:\Users\..."*

### Legitimate Distinction:
A project may legitimately document its own **production deployment infrastructure** (e.g., *"Production inference is deployed on AWS EC2 G5 instances with NVIDIA A10G GPUs"*).
This information may only be disclosed if:
1. It is explicitly documented in an authorized project evidence record.
2. It is genuinely part of the project's production or staging architecture.
3. The user possesses authorized access permissions to that source.
4. The information is directly relevant to the user's inquiry.

---

## 4. Enforcement Mechanisms

1. **Pre-Retrieval Classifier (`AssistantQueryClassifier`)**:
   - Questions targeting personal device info trigger immediate standard refusal:
     > *"I'm here to assist with the currently selected Handover project. I don't provide personal device or environment information through the Project Knowledge Assistant."*
2. **LLM System Prompt Safeguards (`AssistantLLMReasoner`)**:
   - Clear instructions instructing the reasoner that workstation hardware is protected and distinct from project architecture.
3. **Post-Generation Output Sanitizer (`AssistantAnswerValidator`)**:
   - Scans generated answer and claims using regex pattern `_PERSONAL_HARDWARE_RE` and `_PERSONAL_FILE_PATH_RE`.
   - If workstation hardware or local paths appear without backing evidence, they are scrubbed and replaced with `[protected workstation specification]` or `[local file path]`.
   - If the answer consists primarily of leaked workstation specifications, it is replaced with the canonical refusal and status set to `UNSUPPORTED_QUERY`.
