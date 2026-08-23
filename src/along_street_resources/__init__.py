"""Packaged runtime data for Along the Street."""

from importlib.resources import files
from importlib.resources.abc import Traversable


def data_root() -> Traversable:
    """Return the packaged data directory as a traversable resource tree."""

    return files(__package__).joinpath("data")


def data_resource(*parts: str) -> Traversable:
    """Return one packaged data resource without materializing it to a Path."""

    resource = data_root()
    for part in parts:
        resource = resource.joinpath(part)
    return resource


__all__ = ["data_resource", "data_root"]
