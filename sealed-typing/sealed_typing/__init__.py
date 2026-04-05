"""Sealed classes for Python — runtime enforcement + exhaustive matching support."""
from sealed_typing._sealed import (
    assert_exhaustive,
    is_sealed,
    sealed,
    sealed_subclasses,
    verify_dispatch_exhaustive,
)

__all__ = [
    "assert_exhaustive",
    "is_sealed",
    "sealed",
    "sealed_subclasses",
    "verify_dispatch_exhaustive",
]
