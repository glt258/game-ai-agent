"""Deterministic language selection for model-facing human-readable text."""

from __future__ import annotations

import re

OUTPUT_LANGUAGE_CHOICES = ("auto", "zh-CN", "en")
RESOLVED_OUTPUT_LANGUAGES = ("zh-CN", "en")
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def detect_output_language(text: str) -> str:
    """Choose Simplified Chinese when the user text contains CJK characters."""

    if not isinstance(text, str):
        raise TypeError("language detection input must be a string")
    return "zh-CN" if _CJK_RE.search(text) else "en"


def resolve_output_language(selection: str, user_text: str) -> str:
    """Resolve ``auto`` from user text while honoring explicit selection."""

    if selection not in OUTPUT_LANGUAGE_CHOICES:
        raise ValueError("unsupported output language")
    if selection == "auto":
        return detect_output_language(user_text)
    return selection


def ensure_output_language(language: str) -> str:
    """Validate a language already resolved for a request or repair contract."""

    if language not in RESOLVED_OUTPUT_LANGUAGES:
        raise ValueError("request language must be resolved to zh-CN or en")
    return language


def human_language_directive(language: str) -> str:
    """Render a prose-only instruction; it is not an IR field or enum."""

    ensure_output_language(language)
    if language == "zh-CN":
        return "Human-readable prose: Simplified Chinese (zh-CN)."
    return "Human-readable prose: English (en)."


__all__ = [
    "OUTPUT_LANGUAGE_CHOICES",
    "RESOLVED_OUTPUT_LANGUAGES",
    "detect_output_language",
    "ensure_output_language",
    "human_language_directive",
    "resolve_output_language",
]
