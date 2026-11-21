import sys
import os
import uuid
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.session import create_db_engine, create_session_factory
from app.core.config import get_settings
from app.services.storage_factory import build_storage_backend
from app.services.ingestion_worker import IngestionWorkerService
from app.services.document_extraction import DocumentExtractionService
from app.services.ocr import OllamaGLMOCRService
from app.models.job import BackgroundJob
from app.models.evidence import EvidenceItem
from app.models.enums import BackgroundJobStatus, BackgroundJobType
from sqlalchemy import select

settings = get_settings()
engine = create_db_engine(settings)
session_factory = create_session_factory(engine)

ev_id = uuid.UUID("b7d0bb4a-ab02-488e-b784-bbfd625144ce")

with session_factory() as session:
    ev = session.execute(select(EvidenceItem).where(EvidenceItem.id == ev_id)).scalar_one()
    print(f"Evidence: {ev.title}, status: {ev.processing_status}")

    # Reset any failed ingestion jobs for this evidence to queued
    job = session.execute(
        select(BackgroundJob).where(
            BackgroundJob.evidence_id == ev_id,
            BackgroundJob.job_type == BackgroundJobType.DOCUMENT_INGESTION.value,
        )
    ).scalar_one_or_none()
    if job:
        print(f"Resetting Job {job.id} from {job.status} to queued")
        job.status = BackgroundJobStatus.QUEUED.value
        job.error_code = None
        job.error_message = None
        job.locked_by = None
        job.lease_expires_at = None
        session.commit()

storage = build_storage_backend(settings)
ocr_service = OllamaGLMOCRService(
    base_url=settings.ollama.base_url,
    model=settings.ollama.ocr_model,
)
extraction = DocumentExtractionService(
    ocr_service=ocr_service,
    ingestion_settings=settings.ingestion,
)
worker = IngestionWorkerService(
    session_factory=session_factory,
    storage_backend=storage,
    extraction_service=extraction,
    ingestion_settings=settings.ingestion,
    worker_id="test-ingest-worker",
)

print("Running process_next_job()...")
res = worker.process_next_job()
print(f"process_next_job returned: {res}")

with session_factory() as session:
    ev = session.execute(select(EvidenceItem).where(EvidenceItem.id == ev_id)).scalar_one()
    print(f"After ingestion: status={ev.processing_status}, chunk_count={ev.chunk_count}, page_count={ev.page_count}")
