"""Small durable metadata adapter for resuming the Character Studio context."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from .errors import PersistenceIntegrityError


@dataclass(frozen=True)
class CharacterWorkspaceContext:
    request: dict[str, Any]
    plan: dict[str, Any] | None
    updated_at: str


class CharacterWorkspaceRepository:
    """Persist only the typed context needed to re-derive Skill freshness."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def save(
        self,
        character_id: str,
        request: Mapping[str, Any],
        plan: Mapping[str, Any] | None,
    ) -> CharacterWorkspaceContext:
        request_json = _canonical_json(request)
        plan_json = _canonical_json(plan) if plan is not None else None
        updated_at = datetime.now(timezone.utc).isoformat()
        self._connection.execute(
            """
            INSERT INTO character_workspace_context (
                character_id, request_payload_json, plan_payload_json, updated_at
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(character_id) DO UPDATE SET
                request_payload_json = excluded.request_payload_json,
                plan_payload_json = excluded.plan_payload_json,
                updated_at = excluded.updated_at
            """,
            (character_id, request_json, plan_json, updated_at),
        )
        return CharacterWorkspaceContext(
            dict(request), dict(plan) if plan is not None else None, updated_at
        )

    def get(self, character_id: str) -> CharacterWorkspaceContext | None:
        row = self._connection.execute(
            """
            SELECT request_payload_json, plan_payload_json, updated_at
            FROM character_workspace_context WHERE character_id = ?
            """,
            (character_id,),
        ).fetchone()
        if row is None:
            return None
        try:
            request = json.loads(row["request_payload_json"])
            plan = json.loads(row["plan_payload_json"]) if row["plan_payload_json"] else None
        except (TypeError, json.JSONDecodeError) as error:
            raise PersistenceIntegrityError("workspace context JSON is malformed") from error
        if not isinstance(request, Mapping) or (plan is not None and not isinstance(plan, Mapping)):
            raise PersistenceIntegrityError("workspace context JSON is invalid")
        return CharacterWorkspaceContext(
            dict(request), dict(plan) if plan is not None else None, row["updated_at"]
        )


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


__all__ = ["CharacterWorkspaceContext", "CharacterWorkspaceRepository"]
