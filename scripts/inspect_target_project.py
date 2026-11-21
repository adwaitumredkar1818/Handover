import sys
import os
import uuid
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.session import create_db_engine, create_session_factory
from app.core.config import get_settings
from app.models.project import Project
from app.models.evidence import EvidenceItem, EvidenceChunk
from app.models.job import BackgroundJob
from app.models.integration import SourceConnection, SourceAccessPolicy
from app.models.knowledge import KnowledgeItem, KnowledgeEvidenceLink, KnowledgeExtractionRun
from app.models.relationship import KnowledgeEntity, KnowledgeRelationship
from app.services.pipeline_coordinator import PipelineCoordinatorService
from sqlalchemy import select, func

settings = get_settings()
engine = create_db_engine(settings)
session_factory = create_session_factory(engine)

target_id = uuid.UUID("a79345eb-0464-4c8a-bb40-bbce15e9a206")

with session_factory() as session:
    proj = session.get(Project, target_id)
    print(f"Target Project: '{proj.name}' ({proj.id}) | Slug: {proj.slug} | Org: {proj.organisation_id}")
    
    # 1. Evidence breakdown
    ev_items = session.execute(
        select(EvidenceItem).where(EvidenceItem.project_id == target_id).order_by(EvidenceItem.created_at.asc())
    ).scalars().all()
    print(f"\n--- 1. Evidence Items ({len(ev_items)} total) ---")
    for ev in ev_items:
        chunk_cnt = session.execute(
            select(func.count(EvidenceChunk.id)).where(EvidenceChunk.evidence_id == ev.id)
        ).scalar() or 0
        fp = (ev.metadata_json or {}).get("extraction_fingerprint")
        print(f"  [{ev.source_type}] '{ev.title}' (ID: {ev.id})")
        print(f"    Category: {ev.category} | Proc Status: {ev.processing_status} | Index Status: {ev.indexing_status} | Chunks: {chunk_cnt} | Fingerprinted: {fp is not None}")
        if ev.error_code or ev.error_message:
            print(f"    Error: [{ev.error_code}] {ev.error_message}")
            
    # 2. Background Jobs
    jobs = session.execute(
        select(BackgroundJob).where(BackgroundJob.project_id == target_id).order_by(BackgroundJob.created_at.asc())
    ).scalars().all()
    print(f"\n--- 2. Background Jobs ({len(jobs)} total) ---")
    for j in jobs:
        print(f"  * Job {j.id} | Type: {j.job_type} | Status: {j.status} | Attempts: {j.attempt_count}/{j.max_attempts}")
        print(f"    Created: {j.created_at} | Started: {j.started_at} | Completed: {j.completed_at} | Duration: {j.duration_ms}ms")
        print(f"    LockedBy: {j.locked_by} | LeaseExpires: {j.lease_expires_at}")
        if j.payload_json:
            trigger = j.payload_json.get("trigger")
            scope = j.payload_json.get("scope_type")
            ev_id = j.payload_json.get("evidence_id")
            num_evs = len(j.payload_json.get("evidence_ids", [])) if "evidence_ids" in j.payload_json else 0
            print(f"    Payload: trigger={trigger}, scope={scope}, ev_id={ev_id}, batch_ev_count={num_evs}")
        if j.error_code or j.error_message:
            print(f"    ERROR: [{j.error_code}] {j.error_message}")

    # 3. Knowledge Extraction Runs
    k_runs = session.execute(
        select(KnowledgeExtractionRun).where(KnowledgeExtractionRun.project_id == target_id).order_by(KnowledgeExtractionRun.created_at.asc())
    ).scalars().all()
    print(f"\n--- 3. Knowledge Extraction Runs ({len(k_runs)} total) ---")
    for kr in k_runs:
        print(f"  * Run {kr.id} | Status: {kr.status} | Scope: {kr.scope_type} | Categories: {kr.target_categories}")
        print(f"    Created: {kr.created_at} | Completed: {kr.completed_at} | Duration: {kr.duration_ms}ms")
        print(f"    PromptTok: {kr.prompt_tokens} | CompTok: {kr.completion_tokens} | ClaimsPersisted: {kr.claims_persisted} | Rejected: {kr.claims_rejected_ungrounded}")
        if kr.error_code:
            print(f"    Run Error: [{kr.error_code}] {kr.error_message}")

    # 4. Knowledge Items, Entities, Relationships
    k_items = session.execute(
        select(KnowledgeItem).where(KnowledgeItem.project_id == target_id, KnowledgeItem.is_deleted == False)
    ).scalars().all()
    print(f"\n--- 4. Persisted Knowledge ({len(k_items)} items) ---")
    for ki in k_items[:10]:
        print(f"  [{ki.category}] {ki.title} (epistemic={ki.epistemic_status}, model={ki.extraction_model})")

    entities = session.execute(
        select(KnowledgeEntity).where(KnowledgeEntity.project_id == target_id)
    ).scalars().all()
    relationships = session.execute(
        select(KnowledgeRelationship).where(KnowledgeRelationship.project_id == target_id)
    ).scalars().all()
    print(f"  Entities: {len(entities)}, Relationships: {len(relationships)}")
    for e in entities[:10]:
        print(f"    Entity: [{e.entity_type}] {getattr(e, 'canonical_name', getattr(e, 'name', 'unnamed'))}")
    for r in relationships[:10]:
        s_name = getattr(r, 'source_name', getattr(r, 'source_entity_id', 'unknown'))
        t_name = getattr(r, 'target_name', getattr(r, 'target_entity_id', 'unknown'))
        print(f"    Relationship: {s_name} --({r.relationship_type})--> {t_name}")

    # 5. Pipeline Coordinator Status (What the frontend sees)
    pipe_coord = PipelineCoordinatorService(session)
    status = pipe_coord.get_status(target_id)
    print(f"\n--- 5. Pipeline Coordinator Status (Frontend Response) ---")
    print(f"  State: {status.state} ('{status.state_label}')")
    print(f"  is_processing: {status.is_processing}")
    print(f"  stage: {status.stage} ('{status.stage_label}')")
    print(f"  total_evidence_count: {status.total_evidence_count}")
    print(f"  processed_evidence_count: {status.processed_evidence_count}")
    print(f"  queued_evidence_count: {status.queued_evidence_count}")
    print(f"  failed_evidence_count: {status.failed_evidence_count}")
    print(f"  has_existing_graphs: {status.has_existing_graphs}")
    print(f"  error_message: {status.error_message}")
