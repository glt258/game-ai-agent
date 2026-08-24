"""Stable shape errors for the public Character Skill contract."""

from __future__ import annotations


class SkillKitShapeError(ValueError):
    """Raised when a candidate violates the frozen provider shape contract."""

    def __init__(self, code: str, field_path: str, detail: str) -> None:
        self.code = code
        self.field_path = field_path
        self.detail = detail
        self.message = detail
        super().__init__(f"{code} at {field_path}: {detail}")

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "field_path": self.field_path,
            "message": self.message,
            "detail": self.detail,
        }


__all__ = ["SkillKitShapeError"]
