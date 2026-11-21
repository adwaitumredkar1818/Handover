import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.session import create_db_engine, create_session_factory
from app.core.config import get_settings
from app.models.project import Project
from app.models.evidence import EvidenceItem, EvidenceChunk
from app.models.job import BackgroundJob
from app.models.knowledge import KnowledgeItem, KnowledgeExtractionRun
from app.models.relationship import KnowledgeEntity, KnowledgeRelationship
from app.services.pipeline_coordinator import PipelineCoordinatorService
from sqlalchemy import select

settings = get_settings()
engine = create_db_engine(settings)
session_factory = create_session_factory(engine)

for target_id in ["a75d16d8-9a05-448c-a2af-f1672f3c3549", "a79345eb-0464-4c8a-bb40-bbce15e9a206"]:
    with session_factory() as session:
        proj = session.execute(select(Project).where(Project.id == target_id)).scalar_one_or_none()
        print(f"\n==================================================")
        print(f"Project: '{proj.name}' ({proj.id}) | Org: {proj.organisation_id} | Created: {proj.created_at}")
        ev_items = session.execute(select(EvidenceItem).where(EvidenceItem.project_id == target_id)).scalars().all()
        print(f"Evidence items ({len(ev_items)}):")
        for ev in ev_items:
            cat = getattr(ev, 'category', getattr(ev, 'evidence_type', 'unknown'))
            print(f"  - [{getattr(ev, 'source_type', 'unknown')}] '{ev.title}' ({ev.id}) | Category: {cat} | Proc: {ev.processing_status} | Index: {ev.indexing_status}")
            err = getattr(ev, 'error_message', getattr(ev, 'error_detail', None))
            if err:
                print(f"    Error: {err}")
        
        jobs = session.execute(select(BackgroundJob).where(BackgroundJob.project_id == target_id).order_by(BackgroundJob.created_at.desc())).scalars().all()
        print(f"Jobs ({len(jobs)} total):")
        for j in jobs[:5]:
            retries = getattr(j, 'retry_count', getattr(j, 'attempts', 0))
            print(f"  * Job {j.id} | Type: {j.job_type} | Status: {j.status} | Attempts: {retries}/{j.max_attempts} | Created: {j.created_at}")
            err = getattr(j, 'error_message', getattr(j, 'error_detail', getattr(j, 'last_error', None)))
            if err:
                print(f"    Error: {err}")

        k_items = session.execute(select(KnowledgeItem).where(KnowledgeItem.project_id == target_id)).scalars().all()
        entities = session.execute(select(KnowledgeEntity).where(KnowledgeEntity.project_id == target_id)).scalars().all()
        rels = session.execute(select(KnowledgeRelationship).where(KnowledgeRelationship.project_id == target_id)).scalars().all()
        print(f"KnowledgeItems: {len(k_items)}, Entities: {len(entities)}, Relationships: {len(rels)}")

        pipe_coord = PipelineCoordinatorService(session)
        status = pipe_coord.get_status(target_id)
        print(f"Pipeline status: state={status.state}, stage={status.stage}, is_processing={status.is_processing}, has_existing_graphs={status.has_existing_graphs}")
