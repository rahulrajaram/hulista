import pytest
from sealed_typing import sealed, is_sealed, sealed_subclasses, assert_exhaustive


# --- Test sealed class hierarchy ---

@sealed
class Shape:
    pass


class Circle(Shape):
    def __init__(self, radius: float):
        self.radius = radius


class Square(Shape):
    def __init__(self, side: float):
        self.side = side


class Triangle(Shape):
    def __init__(self, base: float, height: float):
        self.base = base
        self.height = height


# --- Tests ---

class TestSealedDecorator:
    def test_sealed_attribute(self):
        assert Shape.__sealed__ is True
        assert Shape.__sealed_module__ == __name__

    def test_is_sealed(self):
        assert is_sealed(Shape)
        assert not is_sealed(Circle)
        assert not is_sealed(int)

    def test_subclasses_registered(self):
        subs = sealed_subclasses(Shape)
        assert Circle in subs
        assert Square in subs
        assert Triangle in subs
        assert len(subs) == 3

    def test_subclasses_returns_frozenset(self):
        subs = sealed_subclasses(Shape)
        assert isinstance(subs, frozenset)

    def test_subclass_outside_module_raises(self):
        """Subclassing in a different module should raise TypeError."""
        # Simulate by temporarily changing __sealed_module__
        original = Shape.__sealed_module__
        Shape.__sealed_module__ = "some.other.module"
        try:
            with pytest.raises(TypeError, match="Cannot subclass sealed class"):
                class Hexagon(Shape):
                    pass
        finally:
            Shape.__sealed_module__ = original

    def test_non_sealed_raises_on_sealed_subclasses(self):
        with pytest.raises(TypeError, match="is not a sealed class"):
            sealed_subclasses(int)

    def test_sealed_on_non_class_raises(self):
        with pytest.raises(TypeError, match="can only be applied to classes"):
            sealed(42)


class TestAssertExhaustive:
    def test_exhaustive_match(self):
        c = Circle(5.0)
        # Should not raise — all subclasses covered
        assert_exhaustive(c, Circle, Square, Triangle)

    def test_non_exhaustive_raises(self):
        c = Circle(5.0)
        with pytest.raises(TypeError, match="Missing handlers for: Triangle"):
            assert_exhaustive(c, Circle, Square)

    def test_non_sealed_value_raises(self):
        with pytest.raises(TypeError, match="is not a subclass of any sealed class"):
            assert_exhaustive(42, int)


class TestMatchIntegration:
    def test_match_case_with_sealed(self):
        def area(shape: Shape) -> float:
            match shape:
                case Circle(radius=r):
                    return 3.14 * r * r
                case Square(side=s):
                    return s * s
                case Triangle(base=b, height=h):
                    return 0.5 * b * h
                case _:
                    raise TypeError(f"Unexpected shape: {shape}")

        assert area(Circle(5.0)) == pytest.approx(78.5)
        assert area(Square(4.0)) == 16.0
        assert area(Triangle(3.0, 4.0)) == 6.0


class TestSealedWithDataclasses:
    def test_sealed_dataclass(self):
        from dataclasses import dataclass

        @sealed
        class Event:
            pass

        @dataclass
        class Click(Event):
            x: int
            y: int

        @dataclass
        class KeyPress(Event):
            key: str

        assert is_sealed(Event)
        subs = sealed_subclasses(Event)
        assert Click in subs
        assert KeyPress in subs

        e = Click(10, 20)
        assert_exhaustive(e, Click, KeyPress)


class TestSealedInheritanceChain:
    def test_sealed_intermediate(self):
        """Sealed at an intermediate level."""
        @sealed
        class Base:
            pass

        class Child(Base):
            pass

        # Child is not sealed itself
        assert not is_sealed(Child)
        assert is_sealed(Base)
        assert Child in sealed_subclasses(Base)
