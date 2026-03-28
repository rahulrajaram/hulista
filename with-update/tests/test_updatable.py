import pytest
from dataclasses import dataclass
from pydantic import Field, PrivateAttr
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

    def test_standalone_invalid_field_raises(self):
        p = Point(1, 2)
        with pytest.raises(TypeError):
            with_update(p, z=3)

    def test_non_dataclass_raises(self):
        with pytest.raises(TypeError):
            with_update("not a dataclass", x=1)


class TestDecoratorValidation:
    def test_non_dataclass_raises(self):
        with pytest.raises(TypeError):
            @updatable
            class NotADataclass:
                pass

    def test_existing_or_raises(self):
        with pytest.raises(TypeError, match="overwrite existing __or__"):
            @updatable
            @dataclass(frozen=True)
            class AlreadyOr:
                x: int

                def __or__(self, other):
                    return self

    def test_existing_with_update_raises(self):
        with pytest.raises(TypeError, match="overwrite existing with_update"):
            @updatable
            @dataclass(frozen=True)
            class AlreadyMethod:
                x: int

                def with_update(self, **changes):
                    return self


# ---------------------------------------------------------------------------
# Pydantic model tests
# ---------------------------------------------------------------------------

pydantic = pytest.importorskip("pydantic")


class TestPydanticUpdatable:
    def test_or_single_field(self):
        from pydantic import BaseModel

        @updatable
        class Config(BaseModel):
            model_config = {"frozen": True}
            host: str = "localhost"
            port: int = 8080

        cfg = Config()
        cfg2 = cfg | {"port": 9090}
        assert cfg2.port == 9090
        assert cfg.port == 8080  # Original unchanged

    def test_or_multiple_fields(self):
        from pydantic import BaseModel

        @updatable
        class Config(BaseModel):
            model_config = {"frozen": True}
            host: str = "localhost"
            port: int = 8080
            debug: bool = False

        cfg = Config()
        cfg2 = cfg | {"port": 9090, "debug": True}
        assert cfg2.port == 9090
        assert cfg2.debug is True
        assert cfg2.host == "localhost"

    def test_with_update_method(self):
        from pydantic import BaseModel

        @updatable
        class Config(BaseModel):
            model_config = {"frozen": True}
            host: str = "localhost"
            port: int = 8080

        cfg = Config()
        cfg2 = cfg.with_update(host="0.0.0.0")
        assert cfg2.host == "0.0.0.0"

    def test_chained_updates(self):
        from pydantic import BaseModel

        @updatable
        class Config(BaseModel):
            model_config = {"frozen": True}
            host: str = "localhost"
            port: int = 8080
            debug: bool = False

        cfg = Config()
        cfg2 = cfg | {"host": "0.0.0.0"} | {"port": 443}
        assert cfg2.host == "0.0.0.0"
        assert cfg2.port == 443

    def test_invalid_field_raises(self):
        from pydantic import BaseModel

        @updatable
        class Config(BaseModel):
            model_config = {"frozen": True}
            host: str = "localhost"

        cfg = Config()
        with pytest.raises(TypeError):
            cfg | {"nonexistent": 42}

    def test_pydantic_operator_validates_and_coerces(self):
        from pydantic import BaseModel

        @updatable
        class Config(BaseModel):
            model_config = {"frozen": True}
            port: int = 8080

        cfg = Config()
        cfg2 = cfg | {"port": "9090"}
        assert cfg2.port == 9090
        assert type(cfg2.port) is int

    def test_pydantic_operator_invalid_type_raises(self):
        from pydantic import BaseModel, ValidationError

        @updatable
        class Config(BaseModel):
            model_config = {"frozen": True}
            port: int = 8080

        cfg = Config()
        with pytest.raises(ValidationError):
            cfg | {"port": "not-a-port"}

    def test_pydantic_standalone_helper_matches_operator_validation(self):
        from pydantic import BaseModel, ValidationError

        @updatable
        class Config(BaseModel):
            model_config = {"frozen": True}
            port: int = 8080

        cfg = Config()
        cfg2 = with_update(cfg, port="9091")
        assert cfg2.port == 9091
        assert type(cfg2.port) is int

        with pytest.raises(ValidationError):
            with_update(cfg, port="nope")

    def test_pydantic_standalone_invalid_field_raises(self):
        from pydantic import BaseModel

        @updatable
        class Config(BaseModel):
            model_config = {"frozen": True}
            host: str = "localhost"

        cfg = Config()
        with pytest.raises(TypeError):
            with_update(cfg, nonexistent=42)

    def test_pydantic_alias_updates_use_alias_keys(self):
        from pydantic import BaseModel

        @updatable
        class Config(BaseModel):
            model_config = {"frozen": True}
            host: str = Field(alias="HOST")

        cfg = Config(HOST="localhost")
        cfg2 = cfg | {"HOST": "0.0.0.0"}
        assert cfg2.host == "0.0.0.0"

        with pytest.raises(TypeError):
            cfg | {"host": "not-allowed-by-name"}

    def test_pydantic_populate_by_name_accepts_field_names(self):
        from pydantic import BaseModel

        @updatable
        class Config(BaseModel):
            model_config = {"frozen": True, "populate_by_name": True}
            host: str = Field(alias="HOST")

        cfg = Config(HOST="localhost")
        cfg2 = cfg.with_update(host="0.0.0.0")
        assert cfg2.host == "0.0.0.0"

    def test_pydantic_private_attrs_are_preserved(self):
        from pydantic import BaseModel

        @updatable
        class Config(BaseModel):
            model_config = {"frozen": True}
            host: str
            _secret: str = PrivateAttr(default="keep")

        cfg = Config(host="localhost")
        cfg._secret = "custom"
        cfg2 = cfg.with_update(host="0.0.0.0")
        assert cfg2._secret == "custom"

    def test_pydantic_fields_set_is_preserved_and_extended(self):
        from pydantic import BaseModel

        @updatable
        class Config(BaseModel):
            model_config = {"frozen": True}
            host: str
            port: int = 8080

        cfg = Config(host="localhost")
        assert cfg.model_fields_set == {"host"}

        cfg2 = cfg.with_update(port=9090)
        assert cfg2.model_fields_set == {"host", "port"}
        assert cfg2.model_dump(exclude_unset=True) == {"host": "localhost", "port": 9090}
