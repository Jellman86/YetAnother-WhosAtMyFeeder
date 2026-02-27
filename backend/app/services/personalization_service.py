from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Optional

import structlog

from app.database import get_db

log = structlog.get_logger()


class PersonalizationService:
    def __init__(
        self,
        *,
        min_feedback_tags: int = 20,
        half_life_days: float = 30.0,
        max_relative_shift: float = 0.35,
        max_absolute_shift: float = 0.2,
        max_feedback_rows: int = 2000,
    ):
        self.min_feedback_tags = max(1, int(min_feedback_tags))
        self.half_life_days = max(1.0, float(half_life_days))
        self.max_relative_shift = max(0.0, float(max_relative_shift))
        self.max_absolute_shift = max(0.0, float(max_absolute_shift))
        self.max_feedback_rows = max(50, int(max_feedback_rows))
        self._decay_lambda = math.log(2.0) / self.half_life_days

    async def rerank(
        self,
        *,
        camera_name: str,
        model_id: str,
        results: list[dict],
        now: Optional[datetime] = None,
    ) -> list[dict]:
        if not camera_name or not model_id or not results:
            return [dict(row) for row in results]

        labels = [str(row.get("label", "")).strip() for row in results if isinstance(row, dict)]
        labels = [label for label in labels if label]
        if not labels:
            return [dict(row) for row in results]

        try:
            raw_feedback_count, feedback_rows = await self._load_feedback_rows(
                camera_name=camera_name,
                model_id=model_id,
                labels=labels,
            )
        except Exception as exc:
            log.warning(
                "Personalization feedback lookup failed; returning base scores",
                camera_name=camera_name,
                model_id=model_id,
                error=str(exc),
            )
            return [dict(row) for row in results]

        return self.rerank_with_feedback(
            results=results,
            feedback_rows=feedback_rows,
            raw_feedback_count=raw_feedback_count,
            now=now,
        )

    def rerank_with_feedback(
        self,
        *,
        results: list[dict],
        feedback_rows: list[dict],
        raw_feedback_count: Optional[int] = None,
        now: Optional[datetime] = None,
    ) -> list[dict]:
        reranked = [dict(row) for row in results if isinstance(row, dict)]
        if len(reranked) < 2:
            return reranked

        effective_raw_count = int(raw_feedback_count if raw_feedback_count is not None else len(feedback_rows))
        if effective_raw_count < self.min_feedback_tags:
            return reranked

        now_utc = now or datetime.now(timezone.utc)
        if now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=timezone.utc)

        score_by_label: dict[str, float] = {}
        label_order: dict[str, int] = {}
        for idx, row in enumerate(reranked):
            label = str(row.get("label", "")).strip()
            if not label:
                continue
            label_order.setdefault(label, idx)
            score_by_label[label] = float(row.get("score") or 0.0)

        label_set = set(label_order.keys())
        if len(label_set) < 2:
            return reranked

        total_by_predicted: dict[str, float] = {}
        pair_by_predicted_corrected: dict[tuple[str, str], float] = {}

        for row in feedback_rows:
            predicted = str(row.get("predicted_label", "")).strip()
            corrected = str(row.get("corrected_label", "")).strip()
            if predicted not in label_set or not corrected or predicted == corrected:
                continue

            created_at = self._parse_created_at(row.get("created_at"), now_utc)
            age_days = max(0.0, (now_utc - created_at).total_seconds() / 86400.0)
            decay_weight = math.exp(-self._decay_lambda * age_days)
            if decay_weight <= 0.0:
                continue

            total_by_predicted[predicted] = total_by_predicted.get(predicted, 0.0) + decay_weight
            if corrected in label_set:
                key = (predicted, corrected)
                pair_by_predicted_corrected[key] = pair_by_predicted_corrected.get(key, 0.0) + decay_weight

        if not pair_by_predicted_corrected:
            return reranked

        adjustments: dict[str, float] = {label: 0.0 for label in label_set}
        labels_in_order = sorted(label_set, key=lambda label: label_order[label])
        for predicted in labels_in_order:
            total_weight = total_by_predicted.get(predicted, 0.0)
            if total_weight <= 0.0:
                continue

            base_score = max(0.0, score_by_label.get(predicted, 0.0))
            transferable = min(self.max_absolute_shift, base_score * self.max_relative_shift)
            if transferable <= 0.0:
                continue

            transferred = 0.0
            for corrected in labels_in_order:
                if corrected == predicted:
                    continue
                pair_weight = pair_by_predicted_corrected.get((predicted, corrected), 0.0)
                if pair_weight <= 0.0:
                    continue
                probability = pair_weight / total_weight
                delta = transferable * probability
                if delta <= 0.0:
                    continue
                adjustments[corrected] += delta
                transferred += delta

            adjustments[predicted] -= transferred

        for row in reranked:
            label = str(row.get("label", "")).strip()
            if not label:
                continue
            adjusted = float(row.get("score") or 0.0) + adjustments.get(label, 0.0)
            row["score"] = max(0.0, min(1.0, adjusted))

        reranked.sort(
            key=lambda row: (
                -float(row.get("score") or 0.0),
                label_order.get(str(row.get("label", "")), 10_000),
            )
        )
        return reranked

    async def _load_feedback_rows(
        self,
        *,
        camera_name: str,
        model_id: str,
        labels: list[str],
    ) -> tuple[int, list[dict]]:
        normalized_labels = sorted({str(label).strip() for label in labels if str(label).strip()})
        if not normalized_labels:
            return 0, []

        async with get_db() as db:
            async with db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name = 'classification_feedback' LIMIT 1"
            ) as cursor:
                table_exists = await cursor.fetchone()
            if not table_exists:
                return 0, []

            async with db.execute(
                """
                SELECT COUNT(*)
                FROM classification_feedback
                WHERE camera_name = ? AND model_id = ?
                """,
                (camera_name, model_id),
            ) as cursor:
                count_row = await cursor.fetchone()
            raw_feedback_count = int(count_row[0]) if count_row and count_row[0] is not None else 0
            if raw_feedback_count <= 0:
                return 0, []

            placeholders = ",".join(["?"] * len(normalized_labels))
            query = f"""
                SELECT created_at, predicted_label, corrected_label
                FROM classification_feedback
                WHERE camera_name = ?
                  AND model_id = ?
                  AND predicted_label IN ({placeholders})
                ORDER BY created_at DESC
                LIMIT ?
            """
            params = [camera_name, model_id, *normalized_labels, self.max_feedback_rows]
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()

        feedback_rows = [
            {
                "created_at": row[0],
                "predicted_label": row[1],
                "corrected_label": row[2],
            }
            for row in rows
        ]
        return raw_feedback_count, feedback_rows

    async def get_status_summary(self) -> dict:
        summary = {
            "personalization_min_feedback_tags": self.min_feedback_tags,
            "personalization_feedback_rows": 0,
            "personalization_active_camera_models": 0,
        }

        async with get_db() as db:
            async with db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name = 'classification_feedback' LIMIT 1"
            ) as cursor:
                table_exists = await cursor.fetchone()
            if not table_exists:
                return summary

            async with db.execute("SELECT COUNT(*) FROM classification_feedback") as cursor:
                count_row = await cursor.fetchone()
            summary["personalization_feedback_rows"] = int(count_row[0]) if count_row and count_row[0] is not None else 0

            async with db.execute(
                """
                SELECT COUNT(*)
                FROM (
                    SELECT camera_name, model_id
                    FROM classification_feedback
                    GROUP BY camera_name, model_id
                    HAVING COUNT(*) >= ?
                )
                """,
                (self.min_feedback_tags,),
            ) as cursor:
                active_row = await cursor.fetchone()
            summary["personalization_active_camera_models"] = int(active_row[0]) if active_row and active_row[0] is not None else 0

        return summary

    @staticmethod
    def _parse_created_at(value, fallback_now: datetime) -> datetime:
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, str):
            text = value.strip()
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            try:
                dt = datetime.fromisoformat(text)
            except ValueError:
                dt = fallback_now
        else:
            dt = fallback_now

        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)


personalization_service = PersonalizationService()
