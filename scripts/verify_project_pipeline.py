import sys
import os
import uuid
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.session import create_db_engine, create_session_factory
from app.core.config import get_settings
from app.models.evidence import EvidenceItem, EvidenceContent
from app.models.job import BackgroundJob
from app.models.enums import BackgroundJobStatus, BackgroundJobType, EvidenceProcessingStatus
from app.services.pipeline_coordinator import PipelineCoordinatorService
from sqlalchemy import select, update

settings = get_settings()
engine = create_db_engine(settings)
session_factory = create_session_factory(engine)

target_project_id = uuid.UUID("a79345eb-0464-4c8a-bb40-bbce15e9a206")
target_evidence_id = uuid.UUID("b7d0bb4a-ab02-488e-b784-bbfd625144ce")

with session_factory() as session:
    coord = PipelineCoordinatorService(session)
    status_before = coord.get_status(target_project_id)
    print("=== Pipeline Status Before ===")
    print(f"State: {status_before.state} ({status_before.state_label})")
    print(f"Stage: {status_before.stage} ({status_before.stage_label})")
    print(f"Total evidence: {status_before.total_evidence_count}, processed: {status_before.processed_evidence_count}, queued: {status_before.queued_evidence_count}")
    print(f"Entities: {status_before.entity_count}, Relationships: {status_before.relationship_count}, Knowledge items: {status_before.knowledge_item_count}")
    print(f"Has existing graphs: {status_before.has_existing_graphs}")

    # Inspect the PDF evidence
    pdf = session.execute(select(EvidenceItem).where(EvidenceItem.id == target_evidence_id)).scalar_one_or_none()
    if pdf:
        print(f"\nPDF Evidence: status={pdf.processing_status}, indexing={pdf.indexing_status}, pages={pdf.page_count}")
        # If still failed, reset it
        if pdf.processing_status in ("failed", "queued", "pending"):
            pdf.processing_status = EvidenceProcessingStatus.QUEUED.value
            pdf.error_code = None
            pdf.error_message = None
            session.execute(
                update(BackgroundJob)
                .where(
                    BackgroundJob.evidence_id == target_evidence_id,
                    BackgroundJob.job_type == BackgroundJobType.DOCUMENT_INGESTION.value
                )
                .values(status=BackgroundJobStatus.CANCELLED.value)
            )
            job = BackgroundJob(
                organisation_id=pdf.organisation_id,
                project_id=pdf.project_id,
                evidence_id=pdf.id,
                job_type=BackgroundJobType.DOCUMENT_INGESTION.value,
                status=BackgroundJobStatus.QUEUED.value,
                priority=30,
                max_attempts=3,
            )
            session.add(job)
            session.commit()
            print(f"Queued fresh ingestion job {job.id} for PDF.")

    # Call trigger_auto_pipeline to ensure deduplication & filtering runs
    scheduled = coord.trigger_auto_pipeline(target_project_id)
    print(f"\nPipelineCoordinator scheduled {scheduled} jobs.")
    
    # Check all active jobs
    jobs = session.execute(
        select(BackgroundJob).where(
            BackgroundJob.project_id == target_project_id,
            BackgroundJob.status.in_([BackgroundJobStatus.QUEUED.value, BackgroundJobStatus.RUNNING.value])
        )
    ).scalars().all()
    print(f"\nActive jobs ({len(jobs)}):")
    for j in jobs:
        print(f"  {j.id} | type={j.job_type:<25} | status={j.status:<10} | ev_id={j.evidence_id}")
