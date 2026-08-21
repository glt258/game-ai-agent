"""Controlled vocabulary for the v0.6.2-A combat knowledge foundation."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


COMBAT_VOCABULARY_SCHEMA_VERSION = "combat-vocabulary/0.6.2-A"
COMBAT_VOCABULARY_DOMAINS = (
    "combat_role",
    "damage_pattern",
    "mechanic",
    "team_position",
)
CombatVocabularyDomain = Literal[
    "combat_role",
    "damage_pattern",
    "mechanic",
    "team_position",
]

_TOKEN_ID_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
_LOOKUP_SEPARATOR_RE = re.compile(r"[\s-]+")


def _clean_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _lookup_key(value: str) -> str:
    """Return the deterministic key used for canonical IDs and aliases."""

    return _LOOKUP_SEPARATOR_RE.sub("_", value.strip().casefold())


class CombatVocabularyEntry(BaseModel):
    """One canonical token and its deterministic aliases."""

    model_config = ConfigDict(extra="forbid")

    id: str
    description: str
    aliases: tuple[str, ...] = ()

    @field_validator("id")
    @classmethod
    def valid_id(cls, value: str) -> str:
        value = _clean_text(value, "id")
        if not _TOKEN_ID_RE.fullmatch(value):
            raise ValueError("id must use lowercase snake_case")
        return value

    @field_validator("description")
    @classmethod
    def valid_description(cls, value: str) -> str:
        return _clean_text(value, "description")

    @field_validator("aliases", mode="before")
    @classmethod
    def valid_aliases(cls, value: object) -> tuple[str, ...]:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple)):
            raise ValueError("aliases must be a list of strings")
        aliases = tuple(_clean_text(item, "alias") for item in value)
        normalized = tuple(_lookup_key(item) for item in aliases)
        if len(normalized) != len(set(normalized)):
            raise ValueError("aliases must not contain duplicates")
        return tuple(sorted(aliases, key=_lookup_key))

    @model_validator(mode="after")
    def validate_aliases_do_not_match_id(self) -> "CombatVocabularyEntry":
        if _lookup_key(self.id) in {_lookup_key(alias) for alias in self.aliases}:
            raise ValueError("aliases must not duplicate the canonical id")
        return self


class CombatVocabulary(BaseModel):
    """Validated, order-independent combat vocabulary."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    domains: dict[str, tuple[CombatVocabularyEntry, ...]]

    @field_validator("schema_version")
    @classmethod
    def valid_schema_version(cls, value: str) -> str:
        value = _clean_text(value, "schema_version")
        if value != COMBAT_VOCABULARY_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must be {COMBAT_VOCABULARY_SCHEMA_VERSION!r}"
            )
        return value

    @model_validator(mode="after")
    def validate_and_order_domains(self) -> "CombatVocabulary":
        expected = set(COMBAT_VOCABULARY_DOMAINS)
        actual = set(self.domains)
        if actual != expected:
            missing = sorted(expected - actual)
            unknown = sorted(actual - expected)
            raise ValueError(
                f"domains must contain exactly {COMBAT_VOCABULARY_DOMAINS}; "
                f"missing={missing}, unknown={unknown}"
            )

        ordered: dict[str, tuple[CombatVocabularyEntry, ...]] = {}
        for domain in COMBAT_VOCABULARY_DOMAINS:
            entries = tuple(sorted(self.domains[domain], key=lambda item: item.id))
            ids = [entry.id for entry in entries]
            if len(ids) != len(set(ids)):
                raise ValueError(f"{domain} must not contain duplicate token IDs")

            lookup_values: dict[str, str] = {}
            for entry in entries:
                for value in (entry.id, *entry.aliases):
                    key = _lookup_key(value)
                    previous = lookup_values.get(key)
                    if previous is not None and previous != entry.id:
                        raise ValueError(
                            f"{domain} contains colliding token ID or alias {value!r} "
                            f"for {previous!r} and {entry.id!r}"
                        )
                    lookup_values[key] = entry.id
            ordered[domain] = entries

        object.__setattr__(self, "domains", ordered)
        return self

    @property
    def domain_ids(self) -> tuple[str, ...]:
        return COMBAT_VOCABULARY_DOMAINS

    def tokens(self, domain: CombatVocabularyDomain) -> tuple[CombatVocabularyEntry, ...]:
        self._validate_domain(domain)
        return self.domains[domain]

    def canonical_id(self, domain: CombatVocabularyDomain, value: str) -> str:
        """Resolve a canonical ID or alias, rejecting unknown tokens."""

        self._validate_domain(domain)
        value = _clean_text(value, "token")
        key = _lookup_key(value)
        for entry in self.domains[domain]:
            if key == _lookup_key(entry.id) or key in {
                _lookup_key(alias) for alias in entry.aliases
            }:
                return entry.id
        raise ValueError(f"unknown {domain} combat vocabulary token: {value!r}")

    def _validate_domain(self, domain: str) -> None:
        if domain not in COMBAT_VOCABULARY_DOMAINS:
            raise ValueError(f"unknown combat vocabulary domain: {domain!r}")


__all__ = [
    "COMBAT_VOCABULARY_DOMAINS",
    "COMBAT_VOCABULARY_SCHEMA_VERSION",
    "CombatVocabulary",
    "CombatVocabularyDomain",
    "CombatVocabularyEntry",
]
