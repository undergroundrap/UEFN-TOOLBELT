"""The WO-002 Session B evidence artifact must stay machine-checkable.

This is deliberately a small, structural contract over one JSON file: it proves
the artifact parses, is sanitized, records every required state with the only
three permitted verdicts, and keeps the three external conclusions independent.

It is not another prose-parsing or adversarial-language system. A negative
external result is a legitimate terminal outcome, so nothing here asserts that
any particular state passed - only that each one is recorded honestly and
cannot be satisfied by a different state's evidence.
"""

from __future__ import annotations

import copy
import json
import pathlib
import re

import pytest

_EVIDENCE = (
    pathlib.Path(__file__).resolve().parents[1]
    / "docs" / "audits" / "evidence"
    / "2026-08-27-wo002-session-b-official-mcp.json"
)

_STATES = {"passed", "failed", "not_tested"}
_EXTERNAL = ("externally_listable", "externally_describable", "externally_callable")
_PROBES = (
    "list_toolsets()",
    "describe_toolset(UEFN_Toolbelt)",
    "call_tool(toolbelt_list_tools, category=MCP Bridge)",
    "call_tool(toolbelt_describe_tool, tool_name=epic_mcp_status)",
    "call_tool(toolbelt_run_tool, tool_name=epic_mcp_status, "
    "empty json object arguments)",
)
_PHASES = ("before_official_probes", "during_official_probes",
           "after_official_probes")
_META_TOOLS = ("toolbelt_list_tools", "toolbelt_describe_tool",
               "toolbelt_run_tool")
_CLEANUP = (
    "level_mutated_or_saved", "fortnite_launched", "play_session_started",
    "custom_bridge_started", "handoff_absent", "ports_8765_8770_closed",
    "temporary_probe_client_removed", "official_test_client_left_running",
    "initial_official_server_state_restored",
)
# Field names that must never appear, and values that would leak the machine.
_FORBIDDEN_KEYS = {
    "mcp-session-id", "mcp_session_id", "session_id", "sessionid",
    "authorization", "cookie", "set-cookie", "api_key", "apikey",
    "password", "credential", "credentials", "bearer",
}
_FORBIDDEN_VALUES = (
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),  # email
    re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+(?!<)[^\\/\"]+", re.IGNORECASE),
)


@pytest.fixture(scope="module")
def evidence() -> dict:
    assert _EVIDENCE.exists(), "Session B evidence artifact is missing"
    return json.loads(_EVIDENCE.read_text(encoding="utf-8"))


def _walk(node, path=""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield path + "/" + str(key), key, value
            yield from _walk(value, path + "/" + str(key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield path + "[" + str(index) + "]", None, value
            yield from _walk(value, path + "[" + str(index) + "]")


def test_evidence_parses_and_declares_its_identity(evidence) -> None:
    assert evidence["schema_version"] == 1
    assert evidence["sanitized"] is True
    assert evidence["work_order"] == "WO-002"
    assert evidence["session"] == "Session B"
    assert evidence["baseline_commit"] == (
        "d1a2c810126ba6c9e14891da1b25cb198c1d45c7"
    )
    assert evidence["initial_state"]["project"] == "TOOL_TEST"


def test_every_recorded_state_uses_the_permitted_vocabulary(evidence) -> None:
    """No state may be recorded as anything but passed/failed/not_tested."""
    offenders = []
    for path, key, value in _walk(evidence):
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        if key in _EXTERNAL or key in _CLEANUP or key in _META_TOOLS:
            if value not in _STATES:
                offenders.append(path + " = " + repr(value))
    assert not offenders, "states outside the vocabulary: " + repr(offenders)


@pytest.mark.parametrize("state", _EXTERNAL)
def test_each_external_state_is_recorded(evidence, state) -> None:
    assert evidence["external_official_mcp"][state] in _STATES


_TOOLSET_NAME = "UEFN_Toolbelt"
_META_SIGNATURES = _META_TOOLS


def _probe(evidence, label):
    for record in evidence["official_probes"]:
        if record["probe"] == label:
            return record
    return None


def _response_text(record):
    """The text content of a stored response envelope."""
    body = record.get("sanitized_response_envelope") or {}
    parts = (body.get("result") or {}).get("content") or []
    return "".join(part.get("text", "") for part in parts
                   if isinstance(part, dict))


def _probe_succeeded(record):
    """None when the probe is absent; otherwise whether it carried no error."""
    if record is None:
        return None
    if record.get("is_error_envelope"):
        return False
    body = record.get("sanitized_response_envelope") or {}
    if "error" in body:
        return False
    return not (body.get("result") or {}).get("isError", False)


def _derive_external(evidence):
    """Recompute each external verdict from that state's own raw evidence.

    This is the whole point of the artifact: a verdict is only as good as the
    envelope underneath it. Deriving independently means a verdict edited in
    isolation, or an envelope edited in isolation, stops agreeing.
    """
    derived = {}

    listing = _probe(evidence, _PROBES[0])
    ok = _probe_succeeded(listing)
    if ok is None:
        derived["externally_listable"] = "not_tested"
    else:
        present = _TOOLSET_NAME in _response_text(listing)
        derived["externally_listable"] = "passed" if (ok and present) else "failed"

    describe = _probe(evidence, _PROBES[1])
    ok = _probe_succeeded(describe)
    if ok is None:
        derived["externally_describable"] = "not_tested"
    else:
        text = _response_text(describe)
        signatures = all(name in text for name in _META_SIGNATURES)
        derived["externally_describable"] = (
            "passed" if (ok and signatures) else "failed"
        )

    calls = [_probe(evidence, label) for label in _PROBES[2:]]
    outcomes = [_probe_succeeded(record) for record in calls]
    if any(outcome is None for outcome in outcomes):
        derived["externally_callable"] = "not_tested"
    else:
        derived["externally_callable"] = (
            "passed" if all(outcomes) else "failed"
        )
    return derived


def _consistency_offenders(evidence):
    """Recorded verdicts that disagree with their own probe evidence."""
    recorded = evidence["external_official_mcp"]
    derived = _derive_external(evidence)
    return [
        state + ": recorded " + repr(recorded.get(state))
        + " but its own evidence supports " + repr(derived[state])
        for state in _EXTERNAL
        if recorded.get(state) != derived[state]
    ]


def test_external_conclusions_match_their_own_evidence(evidence) -> None:
    """Each verdict is re-derived from its own probe and must agree."""
    assert not _consistency_offenders(evidence), _consistency_offenders(evidence)
    assert "independent_determination_note" in evidence["external_official_mcp"]


def test_external_conclusions_are_all_failed_in_this_artifact(evidence) -> None:
    """The captured proof is a terminal negative; pin it so it cannot drift."""
    recorded = evidence["external_official_mcp"]
    assert [recorded[state] for state in _EXTERNAL] == ["failed"] * 3


def test_official_probe_records_are_distinct(evidence) -> None:
    """One state's evidence can never stand in for another's."""
    probes = evidence["official_probes"]
    labels = [record["probe"] for record in probes]
    assert labels == list(_PROBES), "probe set changed: " + repr(labels)
    assert len(set(labels)) == len(labels), "duplicate probe labels"
    stamps = [record["first_observed_utc"] for record in probes]
    assert all(stamps), "a probe is missing its first-observed timestamp"


@pytest.mark.parametrize("state", _EXTERNAL)
@pytest.mark.parametrize("forged", ("passed", "not_tested"))
def test_upgrading_a_verdict_without_evidence_is_rejected(
    evidence, state, forged
) -> None:
    """Flipping a failed verdict while its failing envelope stands must fail."""
    mutated = copy.deepcopy(evidence)
    assert mutated["external_official_mcp"][state] == "failed"
    mutated["external_official_mcp"][state] = forged
    offenders = _consistency_offenders(mutated)
    assert any(item.startswith(state + ":") for item in offenders), (
        "forging " + state + " as " + forged + " was accepted: " + repr(offenders)
    )


def _forge_success(record):
    """Make one stored envelope look like a successful, fully-populated reply."""
    record["is_error_envelope"] = False
    body = record["sanitized_response_envelope"]
    body.pop("error", None)
    result = body.setdefault("result", {})
    result["isError"] = False
    result["content"] = [{
        "type": "text",
        "text": _TOOLSET_NAME + " " + " ".join(_META_SIGNATURES),
    }]


@pytest.mark.parametrize(("label", "state"), (
    (_PROBES[0], "externally_listable"),
    (_PROBES[1], "externally_describable"),
))
def test_forging_a_success_envelope_is_rejected(evidence, label, state) -> None:
    """A single-probe state cannot have a success envelope under a failed verdict."""
    mutated = copy.deepcopy(evidence)
    _forge_success(_probe(mutated, label))
    offenders = _consistency_offenders(mutated)
    assert any(item.startswith(state + ":") for item in offenders), (
        "a forged success envelope for " + label + " was accepted: "
        + repr(offenders)
    )


def test_callable_requires_every_call_probe(evidence) -> None:
    """externally_callable is only satisfied by all three call_tool records.

    Forging one call probe must NOT flip the verdict - that is the property
    that stops one probe's evidence standing in for another's. Forging all
    three must flip it, which proves the check is reading them at all.
    """
    one = copy.deepcopy(evidence)
    _forge_success(_probe(one, _PROBES[2]))
    assert _derive_external(one)["externally_callable"] == "failed", (
        "one successful call probe was enough to claim callable"
    )
    assert not _consistency_offenders(one)

    every = copy.deepcopy(evidence)
    for label in _PROBES[2:]:
        _forge_success(_probe(every, label))
    assert _derive_external(every)["externally_callable"] == "passed"
    assert any(item.startswith("externally_callable:")
               for item in _consistency_offenders(every)), (
        "forging all three call envelopes left the failed verdict consistent"
    )


def test_the_consistency_check_is_not_vacuous(evidence) -> None:
    """Prove the derivation actually discriminates in both directions."""
    clean = _derive_external(evidence)
    assert clean == dict.fromkeys(_EXTERNAL, "failed")

    missing = copy.deepcopy(evidence)
    missing["official_probes"] = [
        record for record in missing["official_probes"]
        if record["probe"] != _PROBES[0]
    ]
    assert _derive_external(missing)["externally_listable"] == "not_tested"

    listed = copy.deepcopy(evidence)
    record = _probe(listed, _PROBES[0])
    record["is_error_envelope"] = False
    record["sanitized_response_envelope"] = {
        "result": {"content": [{"type": "text", "text": "- " + _TOOLSET_NAME + ": x"}]}
    }
    assert _derive_external(listed)["externally_listable"] == "passed"


@pytest.mark.parametrize("probe", _PROBES)
def test_each_probe_keeps_its_first_result(evidence, probe) -> None:
    record = next(r for r in evidence["official_probes"] if r["probe"] == probe)
    for field in ("first_observed_utc", "sanitized_request_envelope",
                  "sanitized_response_envelope", "decoded_conclusion"):
        assert record.get(field), probe + " is missing " + field
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
                        record["first_observed_utc"]), "timestamp is not UTC"


@pytest.mark.parametrize("phase", _PHASES)
def test_internal_contracts_recorded_for_every_phase(evidence, phase) -> None:
    block = evidence["internal_toolbelt_contracts"][phase]
    for tool in _META_TOOLS:
        assert block[tool] in _STATES
    assert block.get("evidence"), phase + " has no supporting evidence"


@pytest.mark.parametrize("field", _CLEANUP)
def test_cleanup_is_recorded(evidence, field) -> None:
    assert evidence["cleanup"][field] in _STATES


def test_no_forbidden_field_names(evidence) -> None:
    offenders = [
        path for path, key, _value in _walk(evidence)
        if isinstance(key, str) and key.lower() in _FORBIDDEN_KEYS
    ]
    assert not offenders, "sensitive field names present: " + repr(offenders)


def test_no_leaked_values(evidence) -> None:
    """No email address and no un-redacted user path anywhere in the artifact."""
    offenders = []
    for path, _key, value in _walk(evidence):
        if not isinstance(value, str):
            continue
        for pattern in _FORBIDDEN_VALUES:
            if pattern.search(value):
                offenders.append(path)
                break
    assert not offenders, "leaked values at: " + repr(offenders)


def test_the_leak_detector_would_catch_a_regression() -> None:
    """Non-vacuous: prove the sweep rejects what it claims to reject."""
    email, home = _FORBIDDEN_VALUES
    assert email.search("contact me at someone@example.com")
    assert home.search(r"C:\Users\someone\Documents")
    assert not home.search("<user-home>/Documents")
