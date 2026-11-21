"""Mark every KnowledgeItem, VerificationCase, and KnowledgeRelationship as verified in target projects."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.session import create_db_engine
from app.models.enums import (
    EpistemicStatus,
    KnowledgeReviewStatus,
    RelationshipVerificationStatus,
    VerificationCaseStatus,
)
from app.models.knowledge import KnowledgeItem
from app.models.relationship import KnowledgeRelationship
from app.models.verification import VerificationCase

TARGET_PROJECTS: list[tuple[str, uuid.UUID]] = [
    ("handover", uuid.UUID("602506d6-b713-4f77-9d79-88f456e42c44")),
    ("Travello AI", uuid.UUID("d92555ab-e8ad-4ab5-96a7-3c228c98fe1a")),
]


def main() -> None:
    settings = get_settings()
    engine = create_db_engine(settings)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    now = datetime.now(UTC)

    with SessionLocal() as db:
        project_ids = [pid for _, pid in TARGET_PROJECTS]

        ki_res = db.execute(
            update(KnowledgeItem)
            .where(KnowledgeItem.project_id.in_(project_ids))
            .values(
                epistemic_status=EpistemicStatus.HUMAN_VERIFIED.value,
                review_status=KnowledgeReviewStatus.APPROVED.value,
            )
        )
        vc_res = db.execute(
            update(VerificationCase)
            .where(VerificationCase.project_id.in_(project_ids))
            .values(case_status=VerificationCaseStatus.VERIFIED.value)
        )
        rel_res = db.execute(
            update(KnowledgeRelationship)
            .where(KnowledgeRelationship.project_id.in_(project_ids))
            .values(verification_status=RelationshipVerificationStatus.VERIFIED.value)
        )
        db.commit()

        print(
            f"Updated: KnowledgeItems={ki_res.rowcount}, "
            f"VerificationCases={vc_res.rowcount}, "
            f"KnowledgeRelationships={rel_res.rowcount}"
        )

        for name, pid in TARGET_PROJECTS:
            kis = db.execute(
                select(KnowledgeItem.epistemic_status, KnowledgeItem.review_status, func.count())
                .where(KnowledgeItem.project_id == pid)
                .group_by(KnowledgeItem.epistemic_status, KnowledgeItem.review_status)
            ).all()
            vcs = db.execute(
                select(VerificationCase.case_status, func.count())
                .where(VerificationCase.project_id == pid)
                .group_by(VerificationCase.case_status)
            ).all()
            rels = db.execute(
                select(KnowledgeRelationship.verification_status, func.count())
                .where(KnowledgeRelationship.project_id == pid)
                .group_by(KnowledgeRelationship.verification_status)
            ).all()
            print(f"{name}: KI={kis}, VC={vcs}, REL={rels}")


if __name__ == "__main__":
    main()
