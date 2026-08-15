from __future__ import annotations


class ReferenceCorpusError(Exception):
    """Base exception for the isolated external character reference corpus."""


class ReferenceNotFoundError(ReferenceCorpusError):
    pass


class ReferenceLoadError(ReferenceCorpusError):
    pass


class ReferenceValidationError(ReferenceCorpusError):
    pass


class UnsupportedSchemaVersionError(ReferenceCorpusError):
    pass


class ProvenanceValidationError(ReferenceValidationError):
    pass


class DuplicateReferenceError(ReferenceValidationError):
    pass


class CatalogValidationError(ReferenceValidationError):
    pass
