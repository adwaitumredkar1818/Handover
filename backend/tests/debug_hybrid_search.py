from app.db.session import create_db_engine, create_session_factory
from app.core.config import get_settings
from app.models.project import Project
from app.models.user import User
from app.repositories.organisation import OrganisationRepository
from app.repositories.project import ProjectRepository
from app.repositories.rbac import RbacRepository
from app.repositories.user import UserRepository
from app.schemas.retrieval import ProjectSearchRequest, SearchFiltersRequest
from app.services.rbac import RbacService
from app.services.retrieval import HybridRetrievalService
from app.repositories.chunk import EvidenceChunkRepository
from app.repositories.job import BackgroundJobRepository
from app.services.embedding import OllamaEmbeddingService
from app.services.vector_store import ChromaV2HttpVectorStore
from app.services.audit import AuditService
from sqlalchemy import select
import uuid

settings = get_settings()
engine = create_db_engine(settings)
sf = create_session_factory(engine)
s = sf()
try:
    p_id = uuid.UUID("0f73217a-dbbd-4ef6-92a9-16bace7aaba0")
    alice = s.scalars(select(User).where(User.email.like("alice%"))).first()
    rbac_service = RbacService(
        db_session=s,
        rbac_repository=RbacRepository(s),
        user_repository=UserRepository(s),
        organisation_repository=OrganisationRepository(s),
        project_repository=ProjectRepository(s),
    )
    principal = rbac_service.resolve_principal(user=alice, session_family_id=uuid.uuid4())
    project_ctx = rbac_service.resolve_project_context(project_id=p_id, principal=principal, require_explicit_membership=False)

    from app.repositories.audit import AuditLogRepository
    audit_service = AuditService(audit_repository=AuditLogRepository(s))
    hybrid_svc = HybridRetrievalService(
        session=s,
        settings=settings,
        chunk_repository=EvidenceChunkRepository(s),
        job_repository=BackgroundJobRepository(s),
        embedding_service=OllamaEmbeddingService(
            base_url=settings.ollama.base_url,
            model=settings.ollama.embedding_model,
            batch_size=settings.embedding.batch_size,
            expected_dimensions=settings.embedding.expected_dimensions,
        ),
        vector_store=ChromaV2HttpVectorStore(
            base_url=settings.chroma.base_url,
            tenant=settings.chroma.tenant,
            database=settings.chroma.database,
            collection_prefix=settings.chroma.collection_prefix,
            embedding_model=settings.ollama.embedding_model,
            index_version=settings.chroma.index_version,
            expected_dimensions=settings.embedding.expected_dimensions,
        ),
        audit_service=audit_service,
    )

    req = ProjectSearchRequest(query="PostgreSQL", top_k=5)
    resp = hybrid_svc.search_project(project_ctx=project_ctx, payload=req)
    print("search_project total_returned:", resp.total_returned)
    print("search_project results count:", len(resp.results))
    for r in resp.results:
        print("  - Hit:", r.chunk_id, "| Excerpt:", r.citation.excerpt[:60], "| Score:", r.score)
finally:
    s.close()
