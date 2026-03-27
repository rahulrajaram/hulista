"""Sealed classes for Python — runtime enforcement + exhaustive matching support."""
from sealed_typing._sealed import sealed, is_sealed, sealed_subclasses, assert_exhaustive

__all__ = ["sealed", "is_sealed", "sealed_subclasses", "assert_exhaustive"]
