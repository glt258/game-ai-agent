from dataclasses import dataclass, field


REGISTERED_EVALUATORS = frozenset(
    {
        "has_relevant_responsibility",
        "assignment_match",
        "case_assignment_match",
        "explicit_authorization",
        "active_role_assignment",
        "artist_team_match",
        "incident_assignment_match",
    }
)

CONTEXT_FIELDS = frozenset(
    {
        "active_responsibilities",
        "active_assignments",
        "active_projects",
        "active_cases",
        "active_incidents",
        "authorizations",
        "active_roles",
        "artist_teams",
    }
)


@dataclass(frozen=True)
class KnowledgeContext:
    """Concrete runtime facts supplied by Story/Quest/Case systems.

    The resolver never accepts a caller-provided permission result.  These
    fields are identifiers only; scope matching remains resolver-owned.
    """

    active_responsibilities: frozenset[str] = field(default_factory=frozenset)
    active_assignments: frozenset[str] = field(default_factory=frozenset)
    active_projects: frozenset[str] = field(default_factory=frozenset)
    active_cases: frozenset[str] = field(default_factory=frozenset)
    active_incidents: frozenset[str] = field(default_factory=frozenset)
    authorizations: frozenset[str] = field(default_factory=frozenset)
    active_roles: frozenset[str] = field(default_factory=frozenset)
    artist_teams: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        for name in CONTEXT_FIELDS:
            values = getattr(self, name)
            if isinstance(values, (str, bytes)):
                raise ValueError(f"{name} must contain identifiers, not a string")
            normalized = frozenset(values)
            if any(not isinstance(value, str) or not value for value in normalized):
                raise ValueError(f"{name} must contain non-empty string identifiers")
            object.__setattr__(self, name, normalized)
