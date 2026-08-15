from __future__ import annotations

from enum import Enum


class SourceType(str, Enum):
    OFFICIAL = "official"
    WIKI = "wiki"
    DATABASE = "database"
    MEDIA = "media"
    GUIDE = "guide"
    VIDEO = "video"
    OTHER = "other"


class SourceReliability(str, Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    TERTIARY = "tertiary"
    UNKNOWN = "unknown"


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    PARTIALLY_VERIFIED = "partially_verified"
    UNVERIFIED = "unverified"
    CONFLICTED = "conflicted"


class AnalysisStatus(str, Enum):
    MISSING = "missing"
    PARTIAL = "partial"
    COMPLETED = "completed"


class NormalizedRole(str, Enum):
    ON_FIELD_DPS = "on_field_dps"
    OFF_FIELD_DPS = "off_field_dps"
    BURST_DPS = "burst_dps"
    SUPPORT = "support"
    SUSTAIN = "sustain"
    CONTROL = "control"
    HYBRID = "hybrid"
    UNKNOWN = "unknown"


class OrdinalBand(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VARIABLE = "variable"
    UNKNOWN = "unknown"


class AttackRange(str, Enum):
    MELEE = "melee"
    RANGED = "ranged"
    HYBRID = "hybrid"
    VARIABLE = "variable"
    UNKNOWN = "unknown"
