# AI-9 System-Wide Acceptance Test Plan & Quality Validation Architecture

## 1. Executive Summary & Evaluation Objectives

This document establishes the system-wide acceptance test plan for **The Handover — Project Intelligence Engine** (Phase AI-9). The goal of AI-9 is not to introduce speculative features, but to rigorously evaluate whether the implemented AI system is accurate, reliable, secure, performant, resilient, and useful under realistic operating conditions.

The evaluation covers seven distinct phases:
1. **AI-9.0**: Baseline, Architecture, & Evaluation Infrastructure
2. **AI-9.1**: RAG Quality & Evidence Evaluation (Recall, Precision, MRR, NDCG, Lexical vs. Semantic vs. Hybrid)
3. **AI-9.2**: Agent Intelligence & Delegation Evaluation (Selection Accuracy, Synthesis Improvement, Latency & Token Overhead)
4. **AI-9.3**: Hallucination & Answer Reliability (Citation-to-Claim Mapping, Abstention, Contradiction Detection, Prompt Injection Resistance)
5. **AI-9.4**: Performance, Latency, & Resource Benchmarks (TTFT, Generation Speed, GPU VRAM, Gateway Concurrency Limits)
6. **AI-9.5**: Security & Adversarial Acceptance (RBAC/RLS Tenant Boundaries, ACL Enforcement, Consequential Tool Idempotency)
7. **AI-9.6**: Complete Product Acceptance (End-to-End User Workflows, Browser Interruption Recovery, Process Restart Durability)

---

## 2. Test Environments & System Configuration

- **Host OS**: Windows 11 Home (x86_64)
- **Local Accelerator**: NVIDIA GeForce RTX 4050 Laptop GPU (6 GB VRAM)
- **Primary LLM**: `qwen3:8b` (via local Ollama, 40960 context, 4-bit quant, isolated behind `OLLAMA_MAX_CONCURRENT_AI_JOBS=1`)
- **Embedding Model**: `nomic-embed-text:latest` (768 dimensions)
- **OCR Engine**: `glm-ocr:latest`
- **Database**: PostgreSQL 16 (Port 5432, migration revision 0020)
- **Vector Store**: ChromaDB HTTP Server (Port 8001)
- **Cache & Fast Pub/Sub**: Redis 7.2 (Port 6379)
- **Backend**: FastAPI (Python 3.11, Pydantic v2, SQLAlchemy 2.x, Psycopg 3)
- **Frontend**: Next.js 16.4.6 (React 19, TypeScript strict mode, Tailwind CSS v4)
- **Security Boundary**: Zero synthetic data in user workspaces; isolated benchmark fixtures for controlled evaluation.

---

## 3. Mandatory AI-8.4 Carryover Verification Items

The following three critical guarantees carried forward from AI-8.4 will be independently verified:
1. **Test A — Actual Process Restart**: Start an active multi-step investigation, terminate the backend server process, restart the process, and verify that the investigation state and ordered event history are completely recovered from PostgreSQL.
2. **Test B — Concurrent Tool Execution**: Transmit identical approved consequential tool calls simultaneously from independent worker threads/processes, verifying that PostgreSQL's atomic claim record in `audit_logs` prevents duplicate execution.
3. **Test C — Actual Browser SSE Recovery**: Disconnect the client stream during an active investigation, reconnect with `Last-Event-ID`, and verify seamless stream resumption without message duplication or lost final answers.

---

## 4. Evaluation Methodology & Metric Definitions

### 4.1 RAG Quality Metrics (AI-9.1)
- **Recall@K**: Proportion of ground-truth relevant evidence chunks retrieved within the top $K$ candidates ($K \in \{5, 10\}$).
- **Precision@K**: Proportion of retrieved chunks within the top $K$ that are relevant to the query.
- **Mean Reciprocal Rank (MRR)**: $\frac{1}{|Q|} \sum_{i=1}^{|Q|} \frac{1}{\text{rank}_i}$, measuring the position of the first relevant chunk.
- **Normalized Discounted Cumulative Gain (NDCG@K)**: Evaluates ranked position discount of relevant chunks against ideal ranking.
- **Citation Precision**: Proportion of generated citations $[S\#]$ that directly support the accompanying claim.
- **Retrieval Latency**: Milliseconds elapsed across lexical, semantic, and hybrid ranking stages.

### 4.2 Agent Intelligence Metrics (AI-9.2)
- **Delegation Precision & Recall**: Correctness of specialized agent selection based on technical query facets.
- **Worker Execution Success Rate**: Percentage of spawned agent tasks completing without timeout or unhandled exceptions.
- **Synthesis Quality Delta**: Comparative factual accuracy and specificity of answers with agents enabled vs. disabled.
- **Overhead**: Additional latency (seconds) and token consumption introduced by dynamic worker turns.

### 4.3 Reliability & Hallucination Metrics (AI-9.3)
- **Claim Support Precision**: Percentage of factual claims verified by cited evidence excerpts.
- **Unsupported Claim Rate**: Percentage of claims lacking evidence grounding.
- **Correct Abstention Rate**: Rate at which the system explicitly communicates uncertainty when evidence is missing or insufficient.
- **Contradiction Detection Rate**: Rate at which contradictory source facts are flagged.

### 4.4 Performance & Scalability Metrics (AI-9.4)
- **Time to First Token (TTFT)**: Latency until the first streamed SSE token delta.
- **Generation Speed**: Tokens per second generated during synthesis.
- **Peak VRAM**: VRAM consumption under single-inference semaphore protection.
- **Concurrency Queuing Delay**: Time requests wait when the GPU inference semaphore is occupied.

### 4.5 Security Metrics (AI-9.5)
- **Tenant Boundary Leakage Rate**: Zero tolerance (0%) for cross-tenant or cross-project data access.
- **ACL Enforcement Rate**: 100% compliance with restricted source permissions.
- **Tool Idempotency Enforcement**: 100% prevention of duplicate consequential actions.

---

## 5. Controlled Benchmark Dataset Specification

To test without contaminating user workspaces, an isolated benchmark dataset of 10 canonical test cases will be evaluated:
1. **Direct Factual**: Database engine selection and ACID requirements.
2. **Multi-Document Architecture**: Dual-provider storage architecture and encryption envelope.
3. **Historical / Decision Rationale**: ADR-001 PostgreSQL vs MongoDB trade-offs.
4. **Responsibilities & Ownership**: Cryptographic security and architecture ownership.
5. **Relationship / Dependency**: RLS multi-tenant dependencies across database tables.
6. **Bugs & Risks**: RTX 4050 VRAM contention between OCR and Qwen3 8B.
7. **Multi-Source Evidence**: Cross-checking commit metadata and design documentation.
8. **Insufficient Evidence (Abstention)**: Unrecorded roadmap milestones (system must state missing context).
9. **Ambiguous Query**: Vague technical queries requiring query expansion.
10. **Contradictory Evidence**: Reconciling conflicting configuration values.

---

## 6. Acceptance Criteria Thresholds

| Area | Metric | Minimum Acceptance Target | Optimal Target |
| :--- | :--- | :--- | :--- |
| **Retrieval** | Hybrid Recall@5 | $\ge 80\%$ | $\ge 90\%$ |
| **Retrieval** | Hybrid MRR | $\ge 0.70$ | $\ge 0.85$ |
| **Retrieval** | Hybrid vs. Single-Source | Hybrid $\ge$ Semantic & Lexical | Hybrid $+10\%$ improvement |
| **Agents** | Agent Selection Accuracy | $\ge 85\%$ | $\ge 95\%$ |
| **Reliability** | Claim Support Precision | $\ge 90\%$ | $\ge 95\%$ |
| **Reliability** | Correct Abstention Rate | $100\%$ on unrecorded facts | $100\%$ |
| **Security** | Cross-Project Leakage | $0\%$ (Zero tolerance) | $0\%$ |
| **Security** | Tool Duplicate Execution | $0\%$ (Strictly Idempotent) | $0\%$ |
| **Durability** | State Recovery on Restart | $100\%$ from PostgreSQL | $100\%$ |
