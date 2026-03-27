import pytest
import dataclasses
from dataclasses import dataclass
from with_update import updatable, with_update


@updatable
@dataclass(frozen=True)
class Point:
    x: int
    y: int


@updatable
@dataclass(frozen=True, slots=True)
class State:
    status: str = "idle"
    count: int = 0
    items: tuple = ()


class TestUpdatableDataclass:
    def test_or_single_field(self):
        p = Point(1, 2)
        p2 = p | {"x": 10}
        assert p2 == Point(10, 2)
        assert p == Point(1, 2)  # Original unchanged

    def test_or_multiple_fields(self):
        p = Point(1, 2)
        p2 = p | {"x": 10, "y": 20}
        assert p2 == Point(10, 20)

    def test_with_update_method(self):
        p = Point(1, 2)
        p2 = p.with_update(x=10)
        assert p2 == Point(10, 2)

    def test_or_returns_not_implemented_for_non_dict(self):
        p = Point(1, 2)
        assert p.__or__(42) is NotImplemented

    def test_frozen_slots(self):
        s = State()
        s2 = s | {"status": "running", "count": 1}
        assert s2.status == "running"
        assert s2.count == 1
        assert s.status == "idle"

    def test_chained_updates(self):
        s = State()
        s2 = s | {"status": "running"}
        s3 = s2 | {"count": s2.count + 1}
        s4 = s3 | {"items": s3.items + ("a",)}
        assert s4 == State("running", 1, ("a",))

    def test_invalid_field_raises(self):
        p = Point(1, 2)
        with pytest.raises(TypeError):
            p | {"z": 3}


class TestStandaloneWithUpdate:
    def test_standalone_function(self):
        p = Point(1, 2)
        p2 = with_update(p, x=10)
        assert p2 == Point(10, 2)

    def test_non_dataclass_raises(self):
        with pytest.raises(TypeError):
            with_update("not a dataclass", x=1)


class TestDecoratorValidation:
    def test_non_dataclass_raises(self):
        with pytest.raises(TypeError):
            @updatable
            class NotADataclass:
                pass
