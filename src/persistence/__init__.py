"""Storage adapters for durable, domain-owned records."""

from .character_persistence import CharacterPersistenceService
from .character_skill_persistence import (
    BINDING_CONTRACT_VERSION,
    AssociationRevisionSummary,
    CharacterSkillPersistenceService,
    CharacterSkillRepository,
    CharacterSkillState,
    PersistedAssociation,
    PersistedBinding,
)
from .characters import (
    CHARACTER_REVISION_CONTRACT_VERSION,
    CharacterRepository,
    CharacterRevision,
    CharacterRevisionSummary,
    PersistedCharacter,
    SavedCharacterSummary,
)
from .errors import (
    CharacterNotFoundError,
    CharacterRevisionConflictError,
    CharacterRevisionNotFoundError,
    CharacterSkillPersistenceConflictError,
    PersistenceConfigurationError,
    PersistenceContractUnsupportedError,
    PersistenceError,
    PersistenceIntegrityError,
    PersistenceRecordNotFoundError,
    PersistenceSchemaUnsupportedError,
    PersistenceWriteConflictError,
)
from .historical_reports import (
    HistoricalReportPersistenceService,
    HistoricalReportRepository,
    StoredCharacterKitRoleCoverageReport,
    StoredCharacterSkillAlignmentReport,
    StoredSkillEvaluationReport,
)
from .skill_artifacts import (
    SkillArtifactRepository,
    StoredSkillArtifact,
    StoredSkillArtifactContent,
)
from .sqlite_store import CURRENT_SCHEMA_VERSION, PersistenceUnitOfWork
from .workspace import CharacterWorkspaceContext, CharacterWorkspaceRepository

__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "CHARACTER_REVISION_CONTRACT_VERSION",
    "CharacterNotFoundError",
    "CharacterPersistenceService",
    "CharacterRepository",
    "CharacterRevision",
    "CharacterRevisionConflictError",
    "CharacterRevisionNotFoundError",
    "CharacterSkillPersistenceConflictError",
    "CharacterSkillPersistenceService",
    "CharacterSkillRepository",
    "CharacterSkillState",
    "CharacterRevisionSummary",
    "PersistenceContractUnsupportedError",
    "PersistenceConfigurationError",
    "PersistenceError",
    "PersistenceIntegrityError",
    "PersistenceRecordNotFoundError",
    "PersistenceSchemaUnsupportedError",
    "PersistenceUnitOfWork",
    "PersistenceWriteConflictError",
    "HistoricalReportPersistenceService",
    "HistoricalReportRepository",
    "StoredCharacterKitRoleCoverageReport",
    "StoredCharacterSkillAlignmentReport",
    "StoredSkillEvaluationReport",
    "PersistedCharacter",
    "SavedCharacterSummary",
    "PersistedAssociation",
    "PersistedBinding",
    "AssociationRevisionSummary",
    "BINDING_CONTRACT_VERSION",
    "SkillArtifactRepository",
    "StoredSkillArtifact",
    "StoredSkillArtifactContent",
    "CharacterWorkspaceContext",
    "CharacterWorkspaceRepository",
]
