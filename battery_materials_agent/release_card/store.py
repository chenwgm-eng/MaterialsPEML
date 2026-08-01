"""实验放行卡 PostgreSQL 存储。"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from ..db import get_engine
from ..mdm.reference_dict import ReferenceDictStore
from .models import ReleaseCard


class ReleaseCardStore:
    """放行卡的 PostgreSQL CRUD 存储。"""

    def __init__(self, db_path: str | None = None):
        # db_path 参数保留以兼容旧调用方，迁移至 PostgreSQL 后已忽略，统一使用全局 Engine。
        self.engine = get_engine()
        self._mdm = ReferenceDictStore()

    @staticmethod
    def _serialize(card: ReleaseCard) -> str:
        return json.dumps(card.model_dump(mode="json"), ensure_ascii=False)

    def _validate_status(self, status: str) -> None:
        if self._mdm.get_status_code("release_card", status) is None:
            raise ValueError(f"无效的 status: {status}")

    def _validate_recommendation(self, recommendation: str) -> None:
        if self._mdm.get_dimension("recommendation", recommendation) is None:
            raise ValueError(f"无效的 recommendation: {recommendation}")

    def _validate_evidence_categories(self, evidence_summary: dict) -> None:
        for category in evidence_summary.keys():
            if self._mdm.get_dimension("evidence_category", category) is None:
                raise ValueError(f"无效的 evidence category: {category}")

    def _validate_card(self, card: ReleaseCard) -> None:
        self._validate_status(card.status)
        self._validate_recommendation(card.recommendation)
        self._validate_evidence_categories(card.evidence_summary)

    def create(self, card: ReleaseCard) -> ReleaseCard:
        self._validate_card(card)
        with self.engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO release_card.release_cards
                   (card_id, case_id, project_id, candidate_id, title,
                    recommendation, status, card_json, created_at, updated_at)
                   VALUES (:card_id, :case_id, :project_id, :candidate_id, :title,
                           :recommendation, :status, CAST(:card_json AS JSONB),
                           :created_at, :updated_at)"""),
                {
                    "card_id": card.card_id,
                    "case_id": card.case_id,
                    "project_id": card.project_id,
                    "candidate_id": card.candidate_id,
                    "title": card.title,
                    "recommendation": card.recommendation,
                    "status": card.status,
                    "card_json": self._serialize(card),
                    "created_at": card.created_at.isoformat(),
                    "updated_at": card.updated_at.isoformat(),
                },
            )
        return card

    def get(self, card_id: str) -> ReleaseCard | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT card_json FROM release_card.release_cards WHERE card_id = :card_id"),
                {"card_id": card_id},
            ).fetchone()
        if row is None:
            return None
        card_json = row[0]
        if isinstance(card_json, dict):
            return ReleaseCard.model_validate(card_json)
        return ReleaseCard.model_validate(json.loads(card_json))

    def update(self, card: ReleaseCard) -> ReleaseCard:
        self._validate_card(card)
        with self.engine.begin() as conn:
            conn.execute(
                text("""UPDATE release_card.release_cards
                   SET case_id = :case_id, project_id = :project_id, candidate_id = :candidate_id, title = :title,
                       recommendation = :recommendation, status = :status, card_json = CAST(:card_json AS JSONB),
                       updated_at = :updated_at
                   WHERE card_id = :card_id"""),
                {
                    "case_id": card.case_id,
                    "project_id": card.project_id,
                    "candidate_id": card.candidate_id,
                    "title": card.title,
                    "recommendation": card.recommendation,
                    "status": card.status,
                    "card_json": self._serialize(card),
                    "updated_at": card.updated_at.isoformat(),
                    "card_id": card.card_id,
                },
            )
        return card

    def delete(self, card_id: str) -> bool:
        with self.engine.begin() as conn:
            cur = conn.execute(
                text("DELETE FROM release_card.release_cards WHERE card_id = :card_id"),
                {"card_id": card_id},
            )
        return cur.rowcount > 0

    def list(
        self,
        status: str | None = None,
        recommendation: str | None = None,
        project_id: str | None = None,
        case_id: str | None = None,
        limit: int = 10000,
        offset: int = 0,
    ) -> list[ReleaseCard]:
        query = "SELECT card_json FROM release_card.release_cards WHERE 1=1"
        params: dict[str, Any] = {}

        if status is not None:
            query += " AND status = :status"
            params["status"] = status
        if recommendation is not None:
            query += " AND recommendation = :recommendation"
            params["recommendation"] = recommendation
        if project_id is not None:
            query += " AND project_id = :project_id"
            params["project_id"] = project_id
        if case_id is not None:
            query += " AND case_id = :case_id"
            params["case_id"] = case_id

        query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset

        with self.engine.connect() as conn:
            rows = conn.execute(text(query), params).fetchall()

        result: list[ReleaseCard] = []
        for r in rows:
            card_json = r[0]
            if isinstance(card_json, dict):
                result.append(ReleaseCard.model_validate(card_json))
            else:
                result.append(ReleaseCard.model_validate(json.loads(card_json)))
        return result
