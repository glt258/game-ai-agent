from __future__ import annotations


class ReferenceCorpusError(Exception):
    """Base exception for the isolated external character reference corpus."""


class ReferenceNotFoundError(ReferenceCorpusError):
    pass


class ReferenceLoadError(ReferenceCorpusError):
    pass


class ReferenceValidationError(ReferenceCorpusError):
    pass


class CorpusManifestError(ReferenceValidationError):
    """The corpus manifest is malformed or violates its schema contract."""


class CorpusManifestNotFoundError(CorpusManifestError):
    """A required corpus manifest is absent from the corpus root."""


class CorpusBoundaryError(CorpusManifestError):
    """The filesystem corpus does not match its declared manifest boundary."""

    def __init__(self, errors: str | list[str] | tuple[str, ...]):
        if isinstance(errors, str):
            normalized = (errors,)
        else:
            normalized = tuple(sorted(str(error) for error in errors))
        self.errors = normalized
        super().__init__("corpus boundary validation failed: " + "; ".join(normalized))


class UnsupportedSchemaVersionError(ReferenceCorpusError):
    pass


class ProvenanceValidationError(ReferenceValidationError):
    pass


class DuplicateReferenceError(ReferenceValidationError):
    pass


class CatalogValidationError(ReferenceValidationError):
    pass
