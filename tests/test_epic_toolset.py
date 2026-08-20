"""
Epic Unreal MCP integration — registration honesty and safe degradation.
==============================================================================
Two invariants:

  1. Toolbelt must import and register its 361 tools on a build with no
     ToolsetRegistry at all. Epic's plugin is Experimental and gated behind a
     beta flag, so absence is the common case, not the exceptional one.

  2. register() must never claim success the registry did not grant. Epic's
     register_toolset_class LOGS "Unable to register" and returns normally when
     the name is taken — it does not raise. Observed live on UEFN 42.00:
     the editor logged a refusal while Toolbelt logged "Registered".
"""

from __future__ import annotations

import pytest

from UEFN_Toolbelt import epic_toolset as et


@pytest.fixture(autouse=True)
def _reset():
    """
    Clear module state AND the cross-reload stash. The stash deliberately lives
    on the `unreal` module so a hot-reload cannot clear it — which means it also
    survives between tests unless dropped here.
    """
    import unreal

    def _clean():
        et._TOOLSET_CLASS = None
        et._REGISTERED = False
        # Set to None rather than delattr: conftest's fake `unreal` recreates any
        # attribute on access, so a deleted stash reads back as a MagicMock and
        # every test would look like "already registered".
        setattr(unreal, et._STASH_ATTR, None)

    _clean()
    yield
    _clean()


class _Toolset:
    """Stand-in for the generated uclass."""
    __module__ = "UEFN_Toolbelt.epic_toolset"
    __name__ = "UEFNToolbeltToolset"


def _registry(*, class_registered=False, name_registered=False, on_register=None):
    class _R:
        registered_calls: list = []

        @staticmethod
        def is_available():
            return True

        @staticmethod
        def is_toolset_class_registered(cls):
            return class_registered

        @staticmethod
        def is_toolset_registered(name):
            return name_registered

        @staticmethod
        def register_toolset_class(cls):
            _R.registered_calls.append(cls)
            if on_register:
                on_register()

    return _R


# ── Degradation ───────────────────────────────────────────────────────────────

def test_absent_registry_is_reported_as_skipped_not_error():
    """
    Off-editor there is no toolset_registry module, which is the same shape as a
    user without the Experimental plugin. That must read as "skipped", never as a
    failure — and must never raise, since register_all_tools() calls this while
    361 tools are riding on it.
    """
    result = et.register()

    assert result["status"] == "skipped"
    assert result["registered"] is False
    assert result["reason"], "a skip must say why"


def test_status_is_safe_to_call_without_epic_mcp():
    state = et.status()
    assert state["status"] == "ok"
    assert state["epic_mcp_available"] is False
    assert len(state["meta_tools"]) == 3


# ── Registration honesty ──────────────────────────────────────────────────────

def test_an_unconfirmable_registration_is_reported_honestly(monkeypatch):
    """
    On UEFN 42.00 every query answers False for a Python-defined toolset, even in
    the tick the registry logs "Registering Toolset" for that exact class.

    So a False cannot be reported as a failure — doing that was the previous bug
    inverted, and it made register() announce an error for a registration that
    had just succeeded. The result must say it worked AND that nothing could
    confirm it.
    """
    import unreal
    monkeypatch.setattr(unreal, "ToolsetRegistry",
                        _registry(class_registered=False, name_registered=False))
    monkeypatch.setattr(et, "_build_toolset_class", lambda: _Toolset)
    monkeypatch.setattr(et, "availability", lambda: {"available": True, "reason": ""})

    result = et.register()

    assert result["status"] == "ok"
    assert result["registered"] is True
    assert result["registration_confirmed"] is False


def test_a_false_from_the_registry_is_never_read_as_not_registered(monkeypatch):
    """_is_registered must return None, not False, for an API that always says no."""
    import unreal
    monkeypatch.setattr(unreal, "ToolsetRegistry", _registry(class_registered=False))
    assert et._is_registered(_Toolset) is None


def test_confirmed_registration_reports_success(monkeypatch):
    import unreal
    state = {"registered": False}

    monkeypatch.setattr(unreal, "ToolsetRegistry", type("R", (), {
        "is_available": staticmethod(lambda: True),
        "is_toolset_class_registered": staticmethod(lambda cls: state["registered"]),
        "is_toolset_registered": staticmethod(lambda name: state["registered"]),
        "register_toolset_class": staticmethod(
            lambda cls: state.__setitem__("registered", True)),
    }))
    monkeypatch.setattr(et, "_build_toolset_class", lambda: _Toolset)
    monkeypatch.setattr(et, "availability", lambda: {"available": True, "reason": ""})

    result = et.register()

    assert result["status"] == "ok"
    assert result["registered"] is True
    assert result["registration_confirmed"] is True


def test_already_registered_is_idempotent_and_does_not_rebind(monkeypatch):
    """
    register_all_tools() runs again on every smoke test and hot-reload.
    Re-registering would drop the toolset out from under a connected client.
    """
    import unreal
    reg = _registry(class_registered=True)
    monkeypatch.setattr(unreal, "ToolsetRegistry", reg)
    monkeypatch.setattr(et, "_build_toolset_class", lambda: _Toolset)
    monkeypatch.setattr(et, "availability", lambda: {"available": True, "reason": ""})
    # Our own record of having registered — the registry cannot be asked.
    monkeypatch.setattr(et, "_REGISTERED", True)
    monkeypatch.setattr(unreal, et._STASH_ATTR, _Toolset, raising=False)

    result = et.register()

    assert result["status"] == "ok"
    assert result["already_registered"] is True
    assert reg.registered_calls == [], "must not re-register an active toolset"


def test_unanswerable_registry_is_none_not_false(monkeypatch):
    """'Cannot tell' must stay distinct from 'not registered'."""
    import unreal

    class _Broken:
        @staticmethod
        def is_toolset_class_registered(cls):
            raise RuntimeError("no")

    monkeypatch.setattr(unreal, "ToolsetRegistry", _Broken)
    assert et._is_registered(_Toolset) is None


# ── Surviving a hot-reload ────────────────────────────────────────────────────
# deploy.bat prints a reload that pops every UEFN_Toolbelt module out of
# sys.modules. That destroys this module's class reference while Epic's registry
# keeps holding the NAME, so the next register() built a fresh class the registry
# refused as a duplicate — with nothing left to unregister. Observed live: the
# integration wedged until a full editor restart.

def test_a_registration_from_before_a_reload_is_adopted_not_repeated(monkeypatch):
    """
    A toolset name can be claimed once per editor session. Re-registering is
    refused, and unregister_toolset_class does not release it — called on the
    stashed class it returns without error while the name stays held. UE
    re-instances the UClass by name on reload, so the existing registration
    already serves the new code; asking again only produces two warnings.
    """
    import unreal

    stale = type("UEFNToolbeltToolset", (), {"__module__": "UEFN_Toolbelt.epic_toolset"})
    monkeypatch.setattr(unreal, et._STASH_ATTR, stale, raising=False)

    reg = _registry(class_registered=False)
    monkeypatch.setattr(unreal, "ToolsetRegistry", reg)
    monkeypatch.setattr(et, "_build_toolset_class", lambda: _Toolset)
    monkeypatch.setattr(et, "availability", lambda: {"available": True, "reason": ""})

    result = et.register()

    assert reg.registered_calls == [], "must not re-register a name already claimed"
    assert result["status"] == "ok"
    assert result["registered"] is True
    assert result["already_registered"] is True
    # The stash must now point at the freshly loaded class.
    assert getattr(unreal, et._STASH_ATTR) is _Toolset


def test_the_live_class_is_stashed_where_a_reload_cannot_reach_it(monkeypatch):
    """The stash must live outside UEFN_Toolbelt — sys.modules.pop clears that."""
    import unreal
    monkeypatch.setattr(unreal, et._STASH_ATTR, None, raising=False)

    state = {"registered": False}
    monkeypatch.setattr(unreal, "ToolsetRegistry", type("R", (), {
        "is_available": staticmethod(lambda: True),
        "is_toolset_class_registered": staticmethod(lambda cls: state["registered"]),
        "is_toolset_registered": staticmethod(lambda name: state["registered"]),
        "register_toolset_class": staticmethod(
            lambda cls: state.__setitem__("registered", True)),
    }))
    monkeypatch.setattr(et, "_build_toolset_class", lambda: _Toolset)
    monkeypatch.setattr(et, "availability", lambda: {"available": True, "reason": ""})

    et.register()

    assert getattr(unreal, et._STASH_ATTR, None) is _Toolset


def test_a_first_registration_this_session_actually_registers(monkeypatch):
    """No stash means nobody has claimed the name yet — this must go through."""
    import unreal
    monkeypatch.setattr(unreal, et._STASH_ATTR, None, raising=False)
    reg = _registry(class_registered=False, name_registered=False)
    monkeypatch.setattr(unreal, "ToolsetRegistry", reg)
    monkeypatch.setattr(et, "_build_toolset_class", lambda: _Toolset)
    monkeypatch.setattr(et, "availability", lambda: {"available": True, "reason": ""})

    result = et.register()

    assert reg.registered_calls == [_Toolset]
    assert result["already_registered"] is False


# ── status() must read the registry, not its own bookkeeping ──────────────────

def test_status_prefers_the_registry_but_admits_when_it_cannot_ask(monkeypatch):
    """
    status() reads back from the registry where it can. On UEFN 42.00 it cannot:
    every query answers False for a Python toolset whether or not it is
    registered, so the only honest report is our own record plus
    registration_confirmed=False saying it is unverified.
    """
    import unreal
    monkeypatch.setattr(et, "_TOOLSET_CLASS", _Toolset)
    monkeypatch.setattr(et, "_REGISTERED", True)
    monkeypatch.setattr(unreal, "ToolsetRegistry", _registry(class_registered=False))
    monkeypatch.setattr(et, "availability", lambda: {"available": True, "reason": ""})

    state = et.status()

    assert state["registered"] is True
    assert state["registration_confirmed"] is False,         "an unverifiable answer must not be presented as verified"


def test_status_falls_back_to_the_flag_when_the_registry_cannot_answer(monkeypatch):
    import unreal

    class _Broken:
        @staticmethod
        def is_toolset_class_registered(cls):
            raise RuntimeError("no")

    monkeypatch.setattr(et, "_TOOLSET_CLASS", _Toolset)
    monkeypatch.setattr(et, "_REGISTERED", True)
    monkeypatch.setattr(unreal, "ToolsetRegistry", _Broken)
    monkeypatch.setattr(et, "availability", lambda: {"available": True, "reason": ""})

    state = et.status()

    assert state["registered"] is True
    assert state["registration_confirmed"] is False, "an unconfirmed answer must say so"


def test_status_finds_the_class_through_the_stash_after_a_reload(monkeypatch):
    """After a reload _TOOLSET_CLASS is None, but the stash still has it."""
    import unreal
    monkeypatch.setattr(et, "_TOOLSET_CLASS", None)
    monkeypatch.setattr(unreal, et._STASH_ATTR, _Toolset, raising=False)
    monkeypatch.setattr(unreal, "ToolsetRegistry", _registry(class_registered=True))
    monkeypatch.setattr(et, "availability", lambda: {"available": True, "reason": ""})

    assert et.status()["registered"] is True
