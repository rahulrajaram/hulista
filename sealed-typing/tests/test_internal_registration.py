from __future__ import annotations

from sealed_typing._sealed import sealed, sealed_subclasses


def test_sealed_registers_existing_subclasses() -> None:
    class Base:
        pass

    class Child(Base):
        pass

    sealed_base = sealed(Base)
    assert sealed_subclasses(sealed_base) == frozenset({Child})

