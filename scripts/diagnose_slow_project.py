import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.session import create_db_engine, create_session_factory
from app.core.config import get_settings
from app.models.project import Project
from app.models.evidence import EvidenceItem, EvidenceChunk
from app.models.job import BackgroundJob
from app.models.integration import SourceConnection, SourceAccessPolicy
from app.models.knowledge import KnowledgeItem, KnowledgeEvidenceLink, KnowledgeExtractionRun
from app.models.relationship import KnowledgeEntity, KnowledgeRelationship
from sqlalchemy import select, func

settings = get_settings()
engine = create_db_engine(settings)
session_factory = create_session_factory(engine)

with session_factory() as session:
    print("=================================================================")
    print("PROJECTS AND EVIDENCE SCAN")
    print("=================================================================")
    projects = session.execute(select(Project).order_by(Project.created_at.desc())).scalars().all()
    print(f"Total projects in DB: {len(projects)}")
    
    candidate_projects = []
    for p in projects:
        ev_items = session.execute(
            select(EvidenceItem).where(EvidenceItem.project_id == p.id, EvidenceItem.deleted_at.is_(None))
        ).scalars().all()
        doc_count = sum(1 for e in ev_items if e.source_type == "document_upload")
        gh_count = sum(1 for e in ev_items if e.source_type == "github")
        active_jobs = session.execute(
            select(func.count(BackgroundJob.id)).where(
                BackgroundJob.project_id == p.id,
                BackgroundJob.status.in_(["queued", "running"])
            )
        ).scalar() or 0
        
        print(f"Project: '{p.name}' | Slug: {p.slug} | ID: {p.id}")
        print(f"  Created: {p.created_at} | Org ID: {p.organisation_id}")
        print(f"  Evidence: {len(ev_items)} total (Docs: {doc_count}, GitHub: {gh_count}) | Active Jobs: {active_jobs}")
        
        if gh_count > 0 or doc_count > 0:
            candidate_projects.append((p, ev_items, active_jobs))
            
    print("\n=================================================================")
    print(f"DETAILED PIPELINE TRACE FOR {len(candidate_projects)} CANDIDATE PROJECTS")
    print("=================================================================")
    for p, ev_items, active_jobs in candidate_projects:
        print(f"\n>>> Project: '{p.name}' ({p.id})")
        # List evidence items
        for ev in ev_items:
            chunk_cnt = session.execute(
                select(func.count(EvidenceChunk.id)).where(EvidenceChunk.evidence_id == ev.id)
            ).scalar() or 0
            fp = (ev.metadata_json or {}).get("extraction_fingerprint")
            print(f"  - Evidence: '{ev.title}' (ID: {ev.id})")
            print(f"    Source Type: {ev.source_type} | Category: {ev.category}")
            print(f"    Proc Status: {ev.processing_status} | Index Status: {ev.indexing_status} | Chunks: {chunk_cnt}")
            print(f"    Fingerprint: {fp is not None} | Created: {ev.created_at}")
            
        # List jobs
        jobs = session.execute(
            select(BackgroundJob).where(BackgroundJob.project_id == p.id).order_by(BackgroundJob.created_at.asc())
        ).scalars().all()
        print(f"  Background Jobs ({len(jobs)} total):")
        for j in jobs:
            print(f"    * Job {j.id} | Type: {j.job_type} | Status: {j.status} | Attempts: {j.attempt_count}/{j.max_attempts}")
            print(f"      Created: {j.created_at} | Started: {j.started_at} | Completed: {j.completed_at} | Duration: {j.duration_ms}ms")
            print(f"      LockedBy: {j.locked_by} | LeaseExpires: {j.lease_expires_at}")
            if j.error_code or j.error_message:
                print(f"      ERROR: [{j.error_code}] {j.error_message}")
                
        # List Knowledge Items & Runs
        k_runs = session.execute(
            select(KnowledgeExtractionRun).where(KnowledgeExtractionRun.project_id == p.id).order_by(KnowledgeExtractionRun.created_at.asc())
        ).scalars().all()
        print(f"  Knowledge Extraction Runs ({len(k_runs)}):")
        for kr in k_runs:
            print(f"    * Run {kr.id} | Status: {kr.status} | Scope: {kr.scope_type} | Items Persisted: {kr.claims_persisted} | PromptTok: {kr.prompt_tokens} | CompTok: {kr.completion_tokens} | Duration: {kr.duration_ms}ms")
            if kr.error_code:
                print(f"      Run Error: [{kr.error_code}] {kr.error_message}")
                
        k_count = session.execute(
            select(func.count(KnowledgeItem.id)).where(KnowledgeItem.project_id == p.id, KnowledgeItem.is_deleted == False)
        ).scalar() or 0
        e_count = session.execute(
            select(func.count(KnowledgeEntity.id)).where(KnowledgeEntity.project_id == p.id)
        ).scalar() or 0
        r_count = session.execute(
            select(func.count(KnowledgeRelationship.id)).where(KnowledgeRelationship.project_id == p.id)
        ).scalar() or 0
        print(f"  Summary Knowledge: {k_count} KnowledgeItems, {e_count} Entities, {r_count} Relationships")
