"""Tests for MRO-distance specificity, Union type support, and Protocol support."""
from __future__ import annotations

from typing import Union
from typing import Protocol, runtime_checkable

import pytest

from live_dispatch import AmbiguousDispatchError, Dispatcher
from sealed_typing import sealed


# Module-level classes for verify_exhaustive tests (must be in module scope
# so that get_type_hints() can resolve stringified annotations).
@sealed
class _SealedShape:
    pass


class _SealedRect(_SealedShape):
    pass


class _SealedTri(_SealedShape):
    pass


# ===========================================================================
# 1. Union type support
# ===========================================================================

class TestUnionTypeSupport:
    """Handler registration with Union[A, B] / A | B syntax."""

    def test_union_pipe_syntax_matches_first_type(self) -> None:
        d = Dispatcher("u1")

        @d.register
        def handle(x: int | str) -> str:
            return f"int_or_str:{x}"

        assert d(42) == "int_or_str:42"

    def test_union_pipe_syntax_matches_second_type(self) -> None:
        d = Dispatcher("u2")

        @d.register
        def handle(x: int | str) -> str:
            return f"int_or_str:{x}"

        assert d("hello") == "int_or_str:hello"

    def test_union_typing_syntax(self) -> None:
        d = Dispatcher("u3")

        @d.register
        def handle(x: Union[int, str]) -> str:
            return f"union:{x}"

        assert d(1) == "union:1"
        assert d("a") == "union:a"

    def test_union_does_not_match_unlisted_type(self) -> None:
        d = Dispatcher("u4")

        @d.register
        def handle(x: int | str) -> str:
            return "matched"

        with pytest.raises(TypeError):
            d(3.14)

    def test_union_three_types(self) -> None:
        d = Dispatcher("u5")

        @d.register
        def handle(x: int | str | bytes) -> str:
            return f"got:{type(x).__name__}"

        assert d(1) == "got:int"
        assert d("s") == "got:str"
        assert d(b"b") == "got:bytes"

    def test_union_with_none(self) -> None:
        d = Dispatcher("u6")

        @d.register
        def handle(x: int | None) -> str:
            return f"nullable:{x}"

        assert d(1) == "nullable:1"
        assert d(None) == "nullable:None"

    def test_union_cache_is_invalidated_on_new_registration(self) -> None:
        """Cache must be cleared when a new handler is registered."""
        d = Dispatcher("u_cache")

        @d.register
        def handle_int(x: int) -> str:
            return "int"

        # Warm cache
        assert d(5) == "int"

        @d.register
        def handle_union(x: float | str) -> str:
            return "float_or_str"

        assert d(3.14) == "float_or_str"

    def test_union_multiarg_handler(self) -> None:
        d = Dispatcher("u_multi")

        @d.register
        def handle(x: int | str, y: bytes | float) -> str:
            return f"{type(x).__name__}+{type(y).__name__}"

        assert d(1, b"x") == "int+bytes"
        assert d("s", 2.0) == "str+float"

    def test_union_handlers_info_repr(self) -> None:
        d = Dispatcher("u_repr")

        @d.register
        def handle(x: int | str) -> str:
            return "x"

        info = d.handlers()
        assert len(info) == 1
        assert "Union" in info[0]["types"]["x"]

    def test_union_with_fallback(self) -> None:
        d = Dispatcher("u_fb")

        @d.register
        def handle(x: int | str) -> str:
            return "matched"

        @d.fallback
        def catch(*args: object) -> str:
            return "fallback"

        assert d(3.14) == "fallback"
        assert d(1) == "matched"

    def test_union_with_subclass(self) -> None:
        """A subclass of a union member should match."""
        d = Dispatcher("u_sub")

        @d.register
        def handle(x: Animal | str) -> str:
            return "animal_or_str"

        assert d(Dog()) == "animal_or_str"

    def test_union_typing_union_matches_subclass(self) -> None:
        d = Dispatcher("u_typing_sub")

        @d.register
        def handle(x: Union[int, str]) -> str:
            return "ok"

        # bool is a subclass of int
        assert d(True) == "ok"


# ===========================================================================
# 2. Protocol support
# ===========================================================================

@runtime_checkable
class Drawable(Protocol):
    def draw(self) -> str: ...


@runtime_checkable
class Resizable(Protocol):
    def resize(self, factor: float) -> None: ...


class Circle:
    def draw(self) -> str:
        return "circle"

    def resize(self, factor: float) -> None:
        pass


class Square:
    def draw(self) -> str:
        return "square"


class NotDrawable:
    pass


# A protocol without @runtime_checkable
class NonRuntimeProto(Protocol):
    def fly(self) -> str: ...


class TestProtocolSupport:
    """Handler registration with @runtime_checkable Protocol types."""

    def test_protocol_matches_conforming_object(self) -> None:
        d = Dispatcher("p1")

        @d.register
        def handle(x: Drawable) -> str:
            return x.draw()

        assert d(Circle()) == "circle"
        assert d(Square()) == "square"

    def test_protocol_does_not_match_nonconforming(self) -> None:
        d = Dispatcher("p2")

        @d.register
        def handle(x: Drawable) -> str:
            return x.draw()

        with pytest.raises(TypeError):
            d(NotDrawable())

    def test_non_runtime_protocol_raises_at_registration(self) -> None:
        d = Dispatcher("p_nonruntime")

        with pytest.raises(TypeError, match="runtime_checkable"):
            @d.register
            def handle(x: NonRuntimeProto) -> str:
                return "bad"

    def test_protocol_with_multiple_methods(self) -> None:
        d = Dispatcher("p_multi")

        @d.register
        def handle(x: Resizable) -> str:
            return "resizable"

        assert d(Circle()) == "resizable"

    def test_protocol_and_concrete_type_coexist(self) -> None:
        """A concrete-type handler and a Protocol handler can both be registered."""
        d = Dispatcher("p_coexist")

        @d.register
        def handle_str(x: str) -> str:
            return "string"

        @d.register
        def handle_drawable(x: Drawable) -> str:
            return "drawable"

        assert d("hi") == "string"
        assert d(Circle()) == "drawable"

    def test_protocol_cache_invalidated_on_new_registration(self) -> None:
        d = Dispatcher("p_cache")

        @d.register
        def handle_str(x: str) -> str:
            return "string"

        assert d("warm") == "string"

        @d.register
        def handle_drawable(x: Drawable) -> str:
            return "drawable"

        assert d(Circle()) == "drawable"

    def test_protocol_in_handlers_info(self) -> None:
        d = Dispatcher("p_info")

        @d.register
        def handle(x: Drawable) -> str:
            return "ok"

        info = d.handlers()
        assert info[0]["types"]["x"] == "Drawable"

    def test_protocol_with_fallback(self) -> None:
        d = Dispatcher("p_fb")

        @d.register
        def handle(x: Drawable) -> str:
            return "drawable"

        @d.fallback
        def catch(*args: object) -> str:
            return "fallback"

        assert d(NotDrawable()) == "fallback"
        assert d(Circle()) == "drawable"


# ===========================================================================
# 3. MRO-distance specificity ranking
# ===========================================================================

class Animal:
    pass


class Mammal(Animal):
    pass


class Dog(Mammal):
    pass


class GoldenRetriever(Dog):
    pass


# Module-level helper classes for specificity-ambiguity tests
class _AmbigBase:
    pass


class _AmbigLeft(_AmbigBase):
    pass


class _AmbigRight(_AmbigBase):
    pass


class _AmbigBoth(_AmbigLeft, _AmbigRight):
    pass


# Module-level helper classes for AmbiguousDispatchError repr test
class _ReprA:
    pass


class _ReprB(_ReprA):
    pass


class _ReprC(_ReprA):
    pass


class _ReprD(_ReprB, _ReprC):
    pass


class TestSpecificityRanking:
    """Dispatcher(specificity=True) prefers the most-specific matching handler."""

    def test_specificity_false_is_default(self) -> None:
        """Default mode is priority-based (first registered wins)."""
        d = Dispatcher("spec_default")
        assert d._specificity is False

    def test_specificity_prefers_subclass_handler(self) -> None:
        d = Dispatcher("spec1", specificity=True)

        @d.register
        def handle_animal(x: Animal) -> str:
            return "animal"

        @d.register
        def handle_mammal(x: Mammal) -> str:
            return "mammal"

        # Dog is a Mammal is an Animal; Mammal is closer
        assert d(Dog()) == "mammal"

    def test_specificity_exact_match_wins(self) -> None:
        d = Dispatcher("spec2", specificity=True)

        @d.register
        def handle_animal(x: Animal) -> str:
            return "animal"

        @d.register
        def handle_dog(x: Dog) -> str:
            return "dog"

        assert d(Dog()) == "dog"

    def test_specificity_falls_back_to_ancestor(self) -> None:
        """If only the Animal handler is registered, it should still match."""
        d = Dispatcher("spec3", specificity=True)

        @d.register
        def handle_animal(x: Animal) -> str:
            return "animal"

        assert d(Dog()) == "animal"
        assert d(GoldenRetriever()) == "animal"

    def test_specificity_raises_on_ambiguity(self) -> None:
        """Two handlers with equal total MRO distance should raise AmbiguousDispatchError.

        Handler 1: (Animal, Dog)  -> distances for (Dog(), Dog()) = 2+0 = 2
        Handler 2: (Dog, Animal)  -> distances for (Dog(), Dog()) = 0+2 = 2
        Both equidistant, so dispatch is ambiguous.
        """
        d = Dispatcher("spec4", specificity=True)

        @d.register
        def handle_animal_dog(x: Animal, y: Dog) -> str:
            return "animal+dog"

        @d.register
        def handle_dog_animal(x: Dog, y: Animal) -> str:
            return "dog+animal"

        with pytest.raises(AmbiguousDispatchError):
            d(Dog(), Dog())

    def test_specificity_no_match_returns_none_internally(self) -> None:
        d = Dispatcher("spec5", specificity=True)

        @d.register
        def handle_str(x: str) -> str:
            return "str"

        with pytest.raises(TypeError, match="No handler"):
            d(42)

    def test_specificity_deeper_mro_prefers_most_specific(self) -> None:
        d = Dispatcher("spec6", specificity=True)

        @d.register
        def handle_animal(x: Animal) -> str:
            return "animal"

        @d.register
        def handle_mammal(x: Mammal) -> str:
            return "mammal"

        @d.register
        def handle_dog(x: Dog) -> str:
            return "dog"

        assert d(GoldenRetriever()) == "dog"

    def test_specificity_multiple_args(self) -> None:
        """Specificity is summed across all typed parameters."""
        d = Dispatcher("spec_multi", specificity=True)

        @d.register
        def handle_aa(x: Animal, y: Animal) -> str:
            return "animal+animal"

        @d.register
        def handle_md(x: Mammal, y: Dog) -> str:
            return "mammal+dog"

        # Dog, Dog: handle_md has dist 1+0=1, handle_aa has dist 2+2=4
        assert d(Dog(), Dog()) == "mammal+dog"

    def test_specificity_with_fallback(self) -> None:
        d = Dispatcher("spec_fb", specificity=True)

        @d.register
        def handle_animal(x: Animal) -> str:
            return "animal"

        @d.fallback
        def catch(*args: object) -> str:
            return "fallback"

        assert d(Dog()) == "animal"
        assert d("not an animal") == "fallback"

    def test_specificity_does_not_affect_non_specificity_dispatcher(self) -> None:
        """A default (non-specificity) dispatcher still uses priority order."""
        d = Dispatcher("non_spec")

        @d.register(priority=0)
        def handle_animal(x: Animal) -> str:
            return "animal"

        @d.register(priority=10)
        def handle_mammal(x: Mammal) -> str:
            return "mammal_high_priority"

        # Priority-ordered: mammal handler wins because it has higher priority
        assert d(Dog()) == "mammal_high_priority"

    def test_ambiguous_dispatch_error_is_type_error(self) -> None:
        """AmbiguousDispatchError must be a subclass of TypeError."""
        assert issubclass(AmbiguousDispatchError, TypeError)

    def test_specificity_single_handler_never_ambiguous(self) -> None:
        d = Dispatcher("spec_single", specificity=True)

        @d.register
        def handle_animal(x: Animal) -> str:
            return "animal"

        # Only one handler — can never be ambiguous
        assert d(Dog()) == "animal"

    def test_specificity_with_union_type(self) -> None:
        """Specificity mode should work with Union-annotated handlers."""
        d = Dispatcher("spec_union", specificity=True)

        @d.register
        def handle_animal_or_str(x: Animal | str) -> str:
            return "animal_or_str"

        @d.register
        def handle_mammal(x: Mammal) -> str:
            return "mammal"

        # Mammal handler is more specific for Mammal instances
        assert d(Dog()) == "mammal"
        assert d("hello") == "animal_or_str"

    def test_specificity_with_protocol(self) -> None:
        """Specificity mode should work when a Protocol handler is registered."""
        d = Dispatcher("spec_proto", specificity=True)

        @d.register
        def handle_drawable(x: Drawable) -> str:
            return "drawable"

        @d.register
        def handle_circle(x: Circle) -> str:
            return "circle"

        # Circle handler is more specific (MRO distance 0) than Drawable (Protocol)
        assert d(Circle()) == "circle"
        assert d(Square()) == "drawable"


# ===========================================================================
# 4. AmbiguousDispatchError export
# ===========================================================================

class TestAmbiguousDispatchErrorExport:
    def test_importable_from_package(self) -> None:
        from live_dispatch import AmbiguousDispatchError as E
        assert issubclass(E, TypeError)

    def test_repr_contains_handler_names(self) -> None:
        """Error message should include the names of the conflicting handlers."""
        d = Dispatcher("amb_repr", specificity=True)

        @d.register
        def left(x: Animal, y: Dog) -> str:
            return "animal+dog"

        @d.register
        def right(x: Dog, y: Animal) -> str:
            return "dog+animal"

        with pytest.raises(AmbiguousDispatchError, match="left"):
            d(Dog(), Dog())


# ===========================================================================
# 5. Coverage — exercise uncovered edge-case branches
# ===========================================================================

class TestEdgeCaseCoverage:
    """Tests for lines/branches not covered by the main feature tests."""

    def test_annotated_variadic_parameter_raises(self) -> None:
        """Cover _dispatcher.py: annotated *args or **kwargs raises TypeError."""
        d = Dispatcher("edge_variadic")

        with pytest.raises(TypeError, match="variadic"):
            @d.register
            def handle(*args: int) -> str:
                return "bad"

    def test_non_type_annotation_raises(self) -> None:
        """Cover _dispatcher.py: annotation that is not a type, union, or protocol."""
        d = Dispatcher("edge_nontype")

        with pytest.raises(TypeError, match="plain runtime classes"):
            @d.register
            def handle(x: list[int]) -> str:
                return "bad"

    def test_verify_exhaustive_with_union_handler(self) -> None:
        """Cover _dispatcher.py verify_exhaustive() union branch in type_spec."""
        d = Dispatcher("edge_exhaust_union")

        @d.register
        def handle(x: _SealedRect | _SealedTri) -> str:
            return "shape"

        # Should not raise — both subclasses covered via union
        d.verify_exhaustive(_SealedShape)

    def test_specificity_handler_no_signature(self) -> None:
        """Cover _dispatcher.py specificity path with handler that has no signature."""
        d = Dispatcher("edge_spec_nosig", specificity=True)

        # A builtin callable like `len` has no inspectable signature
        # We register it manually
        d.register(len)
        # Should be able to dispatch without error
        assert d([1, 2, 3]) == 3

    def test_specificity_handler_bind_failure(self) -> None:
        """Cover _dispatcher.py specificity path where sig.bind() fails."""
        d = Dispatcher("edge_spec_bindfail", specificity=True)

        @d.register
        def handle_two(x: int, y: int) -> str:
            return "two_ints"

        @d.register
        def handle_one(x: int) -> str:
            return "one_int"

        # Calling with one int — handle_two bind fails, handle_one matches
        assert d(42) == "one_int"

    def test_non_type_in_union_raises(self) -> None:
        """Cover _dispatcher.py: Union member that is not a type."""
        d = Dispatcher("edge_union_nontype")

        with pytest.raises(TypeError, match="non-type member"):
            @d.register
            def handle(x: Union[int, list[str]]) -> str:
                return "bad"

    def test_handler_matches_bind_failure_returns_false(self) -> None:
        """Cover _Handler.matches() returning False on bind failure."""
        d = Dispatcher("edge_match_fail")

        @d.register
        def handle(x: int, y: str) -> str:
            return "ok"

        @d.fallback
        def catch(*args: object) -> str:
            return "fallback"

        # Wrong arity — bind should fail, fall through to fallback
        assert d(42) == "fallback"
