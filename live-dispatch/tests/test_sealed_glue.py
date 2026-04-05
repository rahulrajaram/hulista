"""Tests for sealed-typing / live-dispatch exhaustiveness glue.

All classes that appear in type annotations must be defined at module level
so that get_type_hints() can resolve them.
"""
from __future__ import annotations

import pytest
from live_dispatch import Dispatcher
from sealed_typing import sealed, verify_dispatch_exhaustive


# ---------------------------------------------------------------------------
# Sealed hierarchies used across tests
# ---------------------------------------------------------------------------

@sealed
class Shape:
    """Simple sealed hierarchy: Shape -> Circle, Square, Triangle."""


class Circle(Shape):
    pass


class Square(Shape):
    pass


class Triangle(Shape):
    pass


@sealed
class Color:
    """Second sealed hierarchy for multi-param and multi-sealed tests."""


class Red(Color):
    pass


class Green(Color):
    pass


class Blue(Color):
    pass


# ---------------------------------------------------------------------------
# verify_exhaustive — per-parameter (param=) mode
# ---------------------------------------------------------------------------

def test_verify_exhaustive_param_full_coverage():
    """param= mode: passes when all subclasses are covered for the given param."""
    d = Dispatcher("shapes")

    @d.register
    def on_circle(x: Circle) -> str:
        return "circle"

    @d.register
    def on_square(x: Square) -> str:
        return "square"

    @d.register
    def on_triangle(x: Triangle) -> str:
        return "triangle"

    # Should not raise
    d.verify_exhaustive(Shape, param="x")


def test_verify_exhaustive_param_missing_subclass():
    """param= mode: fails when a subclass is missing for the given param."""
    d = Dispatcher("shapes")

    @d.register
    def on_circle(x: Circle) -> str:
        return "circle"

    @d.register
    def on_square(x: Square) -> str:
        return "square"

    # Missing Triangle for param 'x'
    with pytest.raises(TypeError, match="Triangle"):
        d.verify_exhaustive(Shape, param="x")


def test_verify_exhaustive_param_wrong_param_name():
    """param= mode: checking a param that no handler uses raises about all subs."""
    d = Dispatcher("shapes")

    @d.register
    def on_circle(x: Circle) -> str:
        return "circle"

    # param='y' — no handler annotates 'y', so coverage is empty
    with pytest.raises(TypeError, match="Missing"):
        d.verify_exhaustive(Shape, param="y")


def test_verify_exhaustive_param_multi_dispatch():
    """param= mode only inspects the named param, even in multi-param handlers."""
    d = Dispatcher("shapes_multi")

    @d.register
    def on_circle_red(x: Circle, y: Red) -> str:
        return "circle+red"

    @d.register
    def on_square_red(x: Square, y: Red) -> str:
        return "square+red"

    @d.register
    def on_triangle_red(x: Triangle, y: Red) -> str:
        return "triangle+red"

    # 'x' is fully covered for Shape
    d.verify_exhaustive(Shape, param="x")

    # 'y' has only Red — not exhaustive for Color
    with pytest.raises(TypeError, match="Missing"):
        d.verify_exhaustive(Color, param="y")


# ---------------------------------------------------------------------------
# verify_exhaustive — backward-compatible (no param) mode
# ---------------------------------------------------------------------------

def test_verify_exhaustive_no_param_full_coverage():
    """Backward compat: no-param mode still works when all subs are covered."""
    d = Dispatcher("shapes_compat")

    @d.register
    def on_circle(x: Circle) -> str:
        return "circle"

    @d.register
    def on_square(x: Square) -> str:
        return "square"

    @d.register
    def on_triangle(x: Triangle) -> str:
        return "triangle"

    d.verify_exhaustive(Shape)  # must not raise


def test_verify_exhaustive_no_param_missing():
    """Backward compat: no-param mode raises when a subclass is missing."""
    d = Dispatcher("shapes_compat")

    @d.register
    def on_circle(x: Circle) -> str:
        return "circle"

    with pytest.raises(TypeError, match="Missing"):
        d.verify_exhaustive(Shape)


def test_verify_exhaustive_not_sealed():
    """Both modes raise TypeError when sealed_base is not a sealed class."""
    d = Dispatcher("test_ns")

    class NotSealed:
        pass

    with pytest.raises(TypeError, match="not a sealed class"):
        d.verify_exhaustive(NotSealed)

    with pytest.raises(TypeError, match="not a sealed class"):
        d.verify_exhaustive(NotSealed, param="x")


def test_verify_exhaustive_union_param():
    """Union annotations count both types for coverage."""
    d = Dispatcher("union_shapes")

    @d.register
    def on_circle_or_square(x: Circle | Square) -> str:
        return "circle_or_square"

    @d.register
    def on_triangle(x: Triangle) -> str:
        return "triangle"

    # Circle and Square covered via Union, Triangle via direct annotation
    d.verify_exhaustive(Shape, param="x")
    d.verify_exhaustive(Shape)  # backward compat also works


# ---------------------------------------------------------------------------
# verify_exhaustive_for
# ---------------------------------------------------------------------------

def test_verify_exhaustive_for_full_coverage():
    """verify_exhaustive_for passes when all params referencing sealed are covered."""
    d = Dispatcher("shapes_for")

    @d.register
    def on_circle(x: Circle) -> str:
        return "circle"

    @d.register
    def on_square(x: Square) -> str:
        return "square"

    @d.register
    def on_triangle(x: Triangle) -> str:
        return "triangle"

    d.verify_exhaustive_for(Shape)  # must not raise


def test_verify_exhaustive_for_fails_on_incomplete_param():
    """verify_exhaustive_for fails when one param has incomplete coverage."""
    d = Dispatcher("shapes_for_fail")

    @d.register
    def on_circle(x: Circle) -> str:
        return "circle"

    @d.register
    def on_square(x: Square) -> str:
        return "square"

    # Triangle missing on param 'x'
    with pytest.raises(TypeError, match="Triangle"):
        d.verify_exhaustive_for(Shape)


def test_verify_exhaustive_for_no_handlers_referencing_sealed():
    """verify_exhaustive_for is a no-op when no handlers reference the sealed type."""
    d = Dispatcher("unrelated")

    @d.register
    def on_int(x: int) -> str:
        return "int"

    # Shape is sealed, but no handler references it — should pass silently
    d.verify_exhaustive_for(Shape)


def test_verify_exhaustive_for_not_sealed():
    """verify_exhaustive_for raises TypeError for non-sealed classes."""
    d = Dispatcher("test_vef_ns")

    class NotSealed:
        pass

    with pytest.raises(TypeError, match="not a sealed class"):
        d.verify_exhaustive_for(NotSealed)


def test_verify_exhaustive_for_multi_param():
    """verify_exhaustive_for checks ALL params that reference the sealed hierarchy."""
    d = Dispatcher("shapes_color")

    # 'x' covers all of Shape; 'y' covers all of Color
    @d.register
    def on_circle_red(x: Circle, y: Red) -> str:
        return "cr"

    @d.register
    def on_square_green(x: Square, y: Green) -> str:
        return "sg"

    @d.register
    def on_triangle_blue(x: Triangle, y: Blue) -> str:
        return "tb"

    # Each param is individually exhaustive
    d.verify_exhaustive_for(Shape)
    d.verify_exhaustive_for(Color)


def test_verify_exhaustive_for_multi_param_incomplete():
    """verify_exhaustive_for fails if only ONE param is incomplete."""
    d = Dispatcher("shapes_color_incomplete")

    @d.register
    def on_circle(x: Circle, y: Red) -> str:
        return "cr"

    @d.register
    def on_square(x: Square, y: Green) -> str:
        return "sg"

    # Triangle missing for 'x'; Blue missing for 'y'
    with pytest.raises(TypeError, match="Triangle|Blue"):
        d.verify_exhaustive_for(Shape)


# ---------------------------------------------------------------------------
# verify_all_sealed
# ---------------------------------------------------------------------------

def test_verify_all_sealed_full_coverage():
    """verify_all_sealed passes when every discovered sealed base is fully covered."""
    d = Dispatcher("all_sealed")

    @d.register
    def on_circle(x: Circle) -> str:
        return "circle"

    @d.register
    def on_square(x: Square) -> str:
        return "square"

    @d.register
    def on_triangle(x: Triangle) -> str:
        return "triangle"

    d.verify_all_sealed()  # must not raise


def test_verify_all_sealed_no_sealed_types():
    """verify_all_sealed is a no-op when handlers have no sealed types."""
    d = Dispatcher("no_sealed")

    @d.register
    def on_int(x: int) -> str:
        return "int"

    @d.register
    def on_str(x: str) -> str:
        return "str"

    d.verify_all_sealed()  # no-op, must not raise


def test_verify_all_sealed_empty_dispatcher():
    """verify_all_sealed is a no-op on an empty dispatcher."""
    d = Dispatcher("empty_all")
    d.verify_all_sealed()  # must not raise


def test_verify_all_sealed_fails_on_incomplete():
    """verify_all_sealed raises when any discovered sealed type is not exhaustive."""
    d = Dispatcher("all_sealed_fail")

    @d.register
    def on_circle(x: Circle) -> str:
        return "circle"

    @d.register
    def on_square(x: Square) -> str:
        return "square"

    # Triangle missing
    with pytest.raises(TypeError, match="Triangle"):
        d.verify_all_sealed()


def test_verify_all_sealed_multi_hierarchy():
    """verify_all_sealed checks all sealed hierarchies present in handlers."""
    d = Dispatcher("multi_hier")

    @d.register
    def h1(x: Circle, y: Red) -> str:
        return "cr"

    @d.register
    def h2(x: Square, y: Green) -> str:
        return "sg"

    @d.register
    def h3(x: Triangle, y: Blue) -> str:
        return "tb"

    # Both Shape and Color hierarchies fully covered
    d.verify_all_sealed()


def test_verify_all_sealed_multi_hierarchy_one_incomplete():
    """verify_all_sealed fails when one of multiple hierarchies is incomplete."""
    d = Dispatcher("multi_hier_fail")

    @d.register
    def h1(x: Circle, y: Red) -> str:
        return "cr"

    @d.register
    def h2(x: Square, y: Green) -> str:
        return "sg"

    # Triangle missing for 'x'; Blue missing for 'y'
    with pytest.raises(TypeError, match="Blue|Triangle"):
        d.verify_all_sealed()


# ---------------------------------------------------------------------------
# verify_dispatch_exhaustive (sealed-typing convenience)
# ---------------------------------------------------------------------------

def test_verify_dispatch_exhaustive_delegates():
    """verify_dispatch_exhaustive calls dispatcher.verify_exhaustive."""
    d = Dispatcher("vde_test")

    @d.register
    def on_circle(x: Circle) -> str:
        return "circle"

    @d.register
    def on_square(x: Square) -> str:
        return "square"

    @d.register
    def on_triangle(x: Triangle) -> str:
        return "triangle"

    # Should not raise
    verify_dispatch_exhaustive(d, Shape)


def test_verify_dispatch_exhaustive_fails_when_missing():
    """verify_dispatch_exhaustive propagates failure from the dispatcher."""
    d = Dispatcher("vde_fail")

    @d.register
    def on_circle(x: Circle) -> str:
        return "circle"

    with pytest.raises(TypeError, match="Missing"):
        verify_dispatch_exhaustive(d, Shape)


def test_verify_dispatch_exhaustive_not_a_dispatcher():
    """verify_dispatch_exhaustive raises TypeError for non-dispatcher objects."""
    with pytest.raises(TypeError, match="verify_exhaustive"):
        verify_dispatch_exhaustive("not a dispatcher", Shape)  # type: ignore[arg-type]


def test_verify_dispatch_exhaustive_not_sealed():
    """verify_dispatch_exhaustive propagates not-sealed error."""
    d = Dispatcher("vde_ns")

    class NotSealed:
        pass

    with pytest.raises(TypeError, match="not a sealed class"):
        verify_dispatch_exhaustive(d, NotSealed)


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

def test_integration_register_verify_unregister_fails():
    """Full lifecycle: register all handlers, verify passes, unregister one, verify fails."""
    d = Dispatcher("integration")

    @d.register
    def on_circle(x: Circle) -> str:
        return "circle"

    @d.register
    def on_square(x: Square) -> str:
        return "square"

    @d.register
    def on_triangle(x: Triangle) -> str:
        return "triangle"

    # All covered
    d.verify_exhaustive(Shape)
    d.verify_exhaustive_for(Shape)
    verify_dispatch_exhaustive(d, Shape)

    # Remove one handler — coverage should break
    d.unregister(on_triangle)

    with pytest.raises(TypeError, match="Triangle"):
        d.verify_exhaustive(Shape)

    with pytest.raises(TypeError, match="Triangle"):
        d.verify_exhaustive_for(Shape)

    with pytest.raises(TypeError, match="Triangle"):
        verify_dispatch_exhaustive(d, Shape)


def test_integration_union_covers_multiple_for_param():
    """A handler with a Union param covers multiple subclasses for that param."""
    d = Dispatcher("union_integration")

    @d.register
    def on_circle_or_square(x: Circle | Square) -> str:
        return "cs"

    @d.register
    def on_triangle(x: Triangle) -> str:
        return "triangle"

    d.verify_exhaustive(Shape, param="x")
    d.verify_exhaustive_for(Shape)
    d.verify_all_sealed()
