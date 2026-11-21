import sys
import os
import uuid
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.session import create_db_engine, create_session_factory
from app.core.config import get_settings
from app.models.evidence import EvidenceItem, EvidenceContent
from app.models.job import BackgroundJob
from app.models.enums import BackgroundJobStatus, BackgroundJobType, EvidenceProcessingStatus
from app.worker import build_worker_service
from app.services.pipeline_coordinator import PipelineCoordinatorService
from sqlalchemy import select, update

settings = get_settings()
engine = create_db_engine(settings)
session_factory = create_session_factory(engine)

target_project_id = uuid.UUID("a79345eb-0464-4c8a-bb40-bbce15e9a206")
target_evidence_id = uuid.UUID("b7d0bb4a-ab02-488e-b784-bbfd625144ce")

print("=== 1. Resetting failed PDF document job ===")
with session_factory() as session:
    ev = session.execute(select(EvidenceItem).where(EvidenceItem.id == target_evidence_id)).scalar_one_or_none()
    if not ev:
        print(f"Error: Evidence {target_evidence_id} not found!")
        sys.exit(1)
    
    print(f"Evidence: {ev.title} (category={ev.category}, mime={ev.mime_type})")
    
    # Reset evidence status to queued
    ev.processing_status = EvidenceProcessingStatus.QUEUED.value
    ev.error_code = None
    ev.error_message = None
    
    # Cancel any previous failed jobs for this evidence
    session.execute(
        update(BackgroundJob)
        .where(
            BackgroundJob.evidence_id == target_evidence_id,
            BackgroundJob.job_type == BackgroundJobType.DOCUMENT_INGESTION.value
        )
        .values(status=BackgroundJobStatus.CANCELLED.value)
    )
    
    # Create fresh ingestion job
    job = BackgroundJob(
        organisation_id=ev.organisation_id,
        project_id=ev.project_id,
        evidence_id=ev.id,
        job_type=BackgroundJobType.DOCUMENT_INGESTION.value,
        status=BackgroundJobStatus.QUEUED.value,
        priority=30,
        max_attempts=3,
    )
    session.add(job)
    session.commit()
    print(f"Created fresh ingestion job {job.id}")

print("\n=== 2. Building worker service and executing ingestion ===")
composite_worker, _ = build_worker_service(settings)

# Process the ingestion job
handled = composite_worker.ingestion_worker.process_next_job()
print(f"Ingestion worker processed job: {handled}")

with session_factory() as session:
    ev = session.execute(select(EvidenceItem).where(EvidenceItem.id == target_evidence_id)).scalar_one()
    print(f"Evidence status after ingestion: {ev.processing_status}")
    print(f"Page count: {ev.page_count}, OCR pages: {ev.ocr_pages_count}")
    content = session.execute(select(EvidenceContent).where(EvidenceContent.evidence_id == target_evidence_id)).scalar_one_or_none()
    print(f"Extracted text length: {len(content.extracted_text) if content else 0}")
    if ev.error_message:
        print(f"Error: {ev.error_code} - {ev.error_message}")

print("\n=== 3. Executing indexing job ===")
handled_index = composite_worker.indexing_worker.process_next_job()
print(f"Indexing worker processed job: {handled_index}")

with session_factory() as session:
    ev = session.execute(select(EvidenceItem).where(EvidenceItem.id == target_evidence_id)).scalar_one()
    print(f"Evidence indexing status: {ev.indexing_status}, chunk_count={ev.chunk_count}")

print("\n=== 4. Checking PipelineCoordinator auto-trigger on project ===")
with session_factory() as session:
    coord = PipelineCoordinatorService(session)
    scheduled = coord.trigger_auto_pipeline(target_project_id)
    print(f"PipelineCoordinator scheduled {scheduled} jobs.")
    
    status = coord.get_status(target_project_id)
    print(f"Pipeline status: state={status.state}, stage={status.stage}, has_existing_graphs={status.has_existing_graphs}")
    print(f"Total evidence: {status.total_evidence_count}, processed: {status.processed_evidence_count}, queued: {status.queued_evidence_count}")
