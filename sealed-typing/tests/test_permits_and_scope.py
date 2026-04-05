"""Tests for @sealed(permits=...) and @sealed(scope="package") features."""
from __future__ import annotations

import sys
import types

import pytest

from sealed_typing import sealed, is_sealed, sealed_subclasses, assert_exhaustive


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_module(name: str) -> types.ModuleType:
    """Return a live module object registered in sys.modules under *name*."""
    mod = types.ModuleType(name)
    mod.__name__ = name
    sys.modules[name] = mod
    return mod


def _subclass_in_module(
    base: type,
    class_name: str,
    module_name: str,
    *,
    extra_bases: str = "",
) -> type:
    """Define a subclass of *base* as if it lives in *module_name*.

    Uses exec so that ``__module__`` is set to *module_name*, matching
    the way real cross-module subclassing triggers ``__init_subclass__``.
    """
    ns: dict[str, object] = {"__name__": module_name, "Base": base}
    exec(
        f"class {class_name}(Base{extra_bases}):\n    pass\n",
        ns,
    )
    cls = ns[class_name]
    assert isinstance(cls, type)
    return cls


# ---------------------------------------------------------------------------
# Tests: permits=list of module objects
# ---------------------------------------------------------------------------

class TestPermitsModuleObjects:
    def setup_method(self):
        self.mod_a = _make_module("permitted_pkg.mod_a")
        self.mod_b = _make_module("permitted_pkg.mod_b")
        self.mod_other = _make_module("some_other_pkg.stuff")

    def test_permits_allows_listed_module(self):
        @sealed(permits=[self.mod_a])
        class Event:
            pass

        # Should not raise.
        Child = _subclass_in_module(Event, "Click", "permitted_pkg.mod_a")
        assert Child in sealed_subclasses(Event)

    def test_permits_blocks_unlisted_module(self):
        @sealed(permits=[self.mod_a])
        class Cmd:
            pass

        with pytest.raises(TypeError, match="Cannot subclass sealed class"):
            _subclass_in_module(Cmd, "BadCmd", "some_other_pkg.stuff")

    def test_permits_multiple_modules(self):
        @sealed(permits=[self.mod_a, self.mod_b])
        class Msg:
            pass

        ChildA = _subclass_in_module(Msg, "MsgA", "permitted_pkg.mod_a")
        ChildB = _subclass_in_module(Msg, "MsgB", "permitted_pkg.mod_b")

        subs = sealed_subclasses(Msg)
        assert ChildA in subs
        assert ChildB in subs

    def test_permits_own_module_always_allowed(self):
        """The sealed class's own module is always allowed even if not in permits."""
        @sealed(permits=[self.mod_a])
        class Base:
            pass

        # __name__ of this test module is the sealed module — must always work.
        class Local(Base):
            pass

        assert Local in sealed_subclasses(Base)

    def test_permits_unlisted_still_blocked(self):
        @sealed(permits=[self.mod_a])
        class Widget:
            pass

        with pytest.raises(TypeError, match="Cannot subclass sealed class"):
            _subclass_in_module(Widget, "Broken", "some_other_pkg.stuff")


# ---------------------------------------------------------------------------
# Tests: permits=list of strings
# ---------------------------------------------------------------------------

class TestPermitsStrings:
    def test_permits_string_exact_match(self):
        @sealed(permits=["allowed.mod"])
        class Node:
            pass

        Child = _subclass_in_module(Node, "Leaf", "allowed.mod")
        assert Child in sealed_subclasses(Node)

    def test_permits_string_prefix_match(self):
        """A string entry acts as a package prefix — sub-modules are also allowed."""
        @sealed(permits=["allowed"])
        class Tree:
            pass

        # "allowed.submod" starts with "allowed." — should be allowed.
        Child = _subclass_in_module(Tree, "Branch", "allowed.submod")
        assert Child in sealed_subclasses(Tree)

    def test_permits_string_blocked(self):
        @sealed(permits=["allowed.mod"])
        class Token:
            pass

        with pytest.raises(TypeError, match="Cannot subclass sealed class"):
            _subclass_in_module(Token, "BadToken", "notallowed.mod")

    def test_permits_empty_list_only_allows_own_module(self):
        """permits=[] means only the declaring module is allowed."""
        @sealed(permits=[])
        class Strict:
            pass

        with pytest.raises(TypeError, match="Cannot subclass sealed class"):
            _subclass_in_module(Strict, "External", "completely.different")

    def test_permits_empty_list_allows_own_module(self):
        @sealed(permits=[])
        class StrictLocal:
            pass

        class Local(StrictLocal):  # same module as this test file — OK
            pass

        assert Local in sealed_subclasses(StrictLocal)


# ---------------------------------------------------------------------------
# Tests: scope="package"
# ---------------------------------------------------------------------------

class TestScopePackage:
    def _make_pkgs(self):
        _make_module("myapp")
        _make_module("myapp.core")
        _make_module("myapp.models")
        _make_module("otherapp")
        _make_module("otherapp.core")

    def test_scope_package_allows_sibling_module(self):
        self._make_pkgs()

        # Sealed class lives in "myapp.core" (simulated via sealed_module attr).
        @sealed(scope="package")
        class Command:
            pass

        # Patch the sealed module so the top-level package becomes "myapp".
        Command.__sealed_module__ = "myapp.core"

        Child = _subclass_in_module(Command, "RunCmd", "myapp.models")
        assert Child in sealed_subclasses(Command)

    def test_scope_package_allows_same_package_root(self):
        self._make_pkgs()

        @sealed(scope="package")
        class Event:
            pass

        Event.__sealed_module__ = "myapp.core"

        Child = _subclass_in_module(Event, "AnyEvent", "myapp")
        assert Child in sealed_subclasses(Event)

    def test_scope_package_blocks_other_package(self):
        self._make_pkgs()

        @sealed(scope="package")
        class Service:
            pass

        Service.__sealed_module__ = "myapp.core"

        with pytest.raises(TypeError, match="Cannot subclass sealed class"):
            _subclass_in_module(Service, "BadSvc", "otherapp.core")

    def test_scope_package_blocks_top_level_mismatch(self):
        self._make_pkgs()

        @sealed(scope="package")
        class Config:
            pass

        Config.__sealed_module__ = "myapp.core"

        with pytest.raises(TypeError, match="Cannot subclass sealed class"):
            _subclass_in_module(Config, "BadCfg", "otherapp")

    def test_scope_package_top_level_package_allowed(self):
        """If sealed class is at the top level (no dots), only that module is allowed."""
        @sealed(scope="package")
        class Root:
            pass

        Root.__sealed_module__ = "singlemod"

        with pytest.raises(TypeError, match="Cannot subclass sealed class"):
            _subclass_in_module(Root, "Child", "othermod")

    def test_scope_package_own_module_allowed(self):
        """The declaring module itself is always allowed under scope="package"."""
        @sealed(scope="package")
        class Base:
            pass

        # This test runs inside the test module — its __name__ is the sealed
        # module, which is the same as Base.__sealed_module__ here.
        class Child(Base):
            pass

        assert Child in sealed_subclasses(Base)


# ---------------------------------------------------------------------------
# Tests: invalid scope value
# ---------------------------------------------------------------------------

class TestInvalidScope:
    def test_unknown_scope_raises_value_error(self):
        with pytest.raises(ValueError, match="Unsupported scope value"):
            @sealed(scope="global")
            class Bad:
                pass

    def test_scope_none_is_same_as_bare_decorator(self):
        """scope=None should behave identically to the bare @sealed form."""
        @sealed(scope=None)
        class Base:
            pass

        class Local(Base):
            pass

        assert Local in sealed_subclasses(Base)

        with pytest.raises(TypeError, match="Cannot subclass sealed class"):
            _subclass_in_module(Base, "External", "totally.different")


# ---------------------------------------------------------------------------
# Tests: permits with invalid entry types
# ---------------------------------------------------------------------------

class TestPermitsInvalidEntries:
    def test_non_module_non_string_in_permits_raises(self):
        with pytest.raises(TypeError, match="permits entries must be modules"):
            @sealed(permits=[42])  # type: ignore[list-item]
            class Bad:
                pass

    def test_class_object_in_permits_raises(self):
        with pytest.raises(TypeError, match="permits entries must be modules"):
            @sealed(permits=[int])  # type: ignore[list-item]
            class Bad2:
                pass


# ---------------------------------------------------------------------------
# Tests: assert_exhaustive works with cross-module subclasses
# ---------------------------------------------------------------------------

class TestAssertExhaustiveCrossModule:
    def test_assert_exhaustive_with_permitted_subclasses(self):
        mod_x = _make_module("xpkg.mod_x")
        mod_y = _make_module("xpkg.mod_y")

        @sealed(permits=[mod_x, mod_y])
        class Result:
            pass

        Ok = _subclass_in_module(Result, "Ok", "xpkg.mod_x")
        Err = _subclass_in_module(Result, "Err", "xpkg.mod_y")

        ok_inst = Ok()
        # Exhaustive — should not raise.
        assert_exhaustive(ok_inst, Ok, Err)

    def test_assert_exhaustive_missing_permitted_subclass_raises(self):
        mod_x = _make_module("zpkg.mod_x_2")
        mod_y = _make_module("zpkg.mod_y_2")

        @sealed(permits=[mod_x, mod_y])
        class Status:
            pass

        Active = _subclass_in_module(Status, "Active", "zpkg.mod_x_2")
        _subclass_in_module(Status, "Inactive", "zpkg.mod_y_2")

        inst = Active()
        with pytest.raises(TypeError, match="Missing handlers for"):
            assert_exhaustive(inst, Active)  # Inactive not listed

    def test_assert_exhaustive_scope_package(self):
        _make_module("apkg")
        _make_module("apkg.v1")
        _make_module("apkg.v2")

        @sealed(scope="package")
        class Message:
            pass

        Message.__sealed_module__ = "apkg.v1"

        Hello = _subclass_in_module(Message, "Hello", "apkg.v1")
        Bye = _subclass_in_module(Message, "Bye", "apkg.v2")

        assert_exhaustive(Hello(), Hello, Bye)

        with pytest.raises(TypeError, match="Missing handlers for"):
            assert_exhaustive(Hello(), Hello)


# ---------------------------------------------------------------------------
# Tests: backward compatibility — bare @sealed unchanged
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_bare_sealed_still_works(self):
        @sealed
        class Shape:
            pass

        class Circle(Shape):
            pass

        assert is_sealed(Shape)
        assert Circle in sealed_subclasses(Shape)

    def test_bare_sealed_still_blocks_other_module(self):
        @sealed
        class Animal:
            pass

        with pytest.raises(TypeError, match="Cannot subclass sealed class"):
            _subclass_in_module(Animal, "Dog", "zoo.module")

    def test_bare_sealed_has_no_permits(self):
        @sealed
        class Plain:
            pass

        assert Plain.__sealed_permits__ is None
        assert Plain.__sealed_scope__ is None

    def test_decorated_with_parens_no_args(self):
        """@sealed() with empty parens behaves like bare @sealed."""
        @sealed()
        class Wrapped:
            pass

        class Local(Wrapped):
            pass

        assert Local in sealed_subclasses(Wrapped)

        with pytest.raises(TypeError, match="Cannot subclass sealed class"):
            _subclass_in_module(Wrapped, "Remote", "remote.pkg")
