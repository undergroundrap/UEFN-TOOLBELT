"""Adversarial contract tests for the custom same-user MCP control plane."""

from __future__ import annotations

import ast
import builtins
import copy
import hashlib
import http.client
import http.server
import importlib.util
import inspect
import io
import json
import os
import queue
import random
import socket
import sys
import threading
import time
import types
import urllib.error
import urllib.request
from pathlib import Path

import pytest


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _response(
    port: int,
    *,
    token: str | None,
    body: bytes = b'{"command":"ping","params":{}}',
    path: str = "/",
    content_type: str = "application/json",
    origin: str | None = None,
    host: str | None = None,
    method: str = "POST",
) -> tuple[int, dict, dict[str, str]]:
    headers = {"Content-Type": content_type}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if origin is not None:
        headers["Origin"] = origin
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=body if method == "POST" else None,
        headers=headers,
        method=method,
    )
    if host is not None:
        request.add_unredirected_header("Host", host)
    try:
        with urllib.request.urlopen(request, timeout=2.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return response.status, payload, dict(response.headers)
    except urllib.error.HTTPError as exc:
        payload = json.loads(exc.read().decode("utf-8"))
        return exc.code, payload, dict(exc.headers)


def _queued_response(bridge, port: int, token: str, body: bytes | None = None):
    completed: queue.Queue = queue.Queue()

    def request() -> None:
        try:
            completed.put(_response(port, token=token, body=body or b'{"command":"ping"}'))
        except Exception as exc:  # pragma: no cover - assertion reports transport failures
            completed.put(exc)

    thread = threading.Thread(target=request, daemon=True)
    thread.start()
    deadline = time.time() + 2.0
    while bridge._command_queue.empty() and time.time() < deadline:
        time.sleep(0.01)
    assert not bridge._command_queue.empty(), "authenticated request was not queued"
    bridge._tick(0.0)
    thread.join(timeout=2.0)
    assert not thread.is_alive()
    result = completed.get_nowait()
    if isinstance(result, Exception):
        raise result
    return result


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    from UEFN_Toolbelt.tools import mcp_bridge

    mcp_bridge.stop_listener()
    monkeypatch.delenv("UEFN_TOOLBELT_MCP_ALLOW_EXECUTE_PYTHON", raising=False)
    monkeypatch.setenv("UEFN_MCP_TOKEN_FILE", str(tmp_path / "mcp_session.json"))
    monkeypatch.setattr(
        mcp_bridge.unreal,
        "register_slate_post_tick_callback",
        lambda callback: object(),
    )
    monkeypatch.setattr(
        mcp_bridge.unreal,
        "unregister_slate_post_tick_callback",
        lambda handle: None,
    )
    yield mcp_bridge
    mcp_bridge.stop_listener()


def _start(bridge) -> tuple[int, str]:
    port = _free_port()
    bridge.start_listener(port)
    handoff = json.loads(bridge._token_handoff_path().read_text(encoding="utf-8"))
    return port, handoff["token"]


def test_listener_requires_correct_auth_before_dispatch(bridge, monkeypatch):
    port, token = _start(bridge)
    dispatched = []
    original = bridge._execute_command

    def capture(command, params):
        dispatched.append(command)
        return original(command, params)

    monkeypatch.setattr(bridge, "_execute_command", capture)

    missing, _, _ = _response(port, token=None, body=b"not json")
    wrong, _, _ = _response(port, token="wrong" * 10, body=b"not json")
    assert missing == 401
    assert wrong == 401
    assert dispatched == []
    assert bridge._command_queue.empty()

    status, payload, _ = _queued_response(bridge, port, token)
    assert status == 200
    assert payload["success"] is True
    assert dispatched == ["ping"]


def test_repeated_auth_rejections_return_stable_json_without_dispatch(
    bridge, monkeypatch
):
    port, _token = _start(bridge)
    dispatched = []
    monkeypatch.setattr(
        bridge,
        "_execute_command",
        lambda command, params: dispatched.append(command),
    )

    for _ in range(25):
        missing, missing_body, _ = _response(port, token=None)
        wrong, wrong_body, _ = _response(port, token="wrong" * 10)
        assert (missing, missing_body) == (
            401,
            {"success": False, "error": "Authentication required"},
        )
        assert (wrong, wrong_body) == (
            401,
            {"success": False, "error": "Authentication required"},
        )

    assert dispatched == []
    assert bridge._command_queue.empty()


def test_request_validation_is_strict_and_browser_closed(bridge):
    port, token = _start(bridge)

    assert _response(port, token=token, path="/elsewhere")[0] == 404
    assert _response(port, token=token, host="localhost:8765")[0] == 400
    assert _response(port, token=token, origin="https://attacker.invalid")[0] == 403
    assert _response(port, token=token, content_type="text/plain")[0] == 415
    assert _response(port, token=token, body=b"not json")[0] == 400
    assert _response(port, token=None, body=b"not json")[0] == 401
    assert _response(port, token=token, method="GET")[0] == 405

    options, _, headers = _response(port, token=None, method="OPTIONS")
    assert options == 403
    assert not any(name.lower().startswith("access-control-") for name in headers)

    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2.0)
    connection.putrequest("POST", "/")
    connection.putheader("Content-Type", "application/json")
    connection.putheader("Authorization", f"Bearer {token}")
    connection.putheader("Content-Length", str(bridge.MAX_CONTENT_LENGTH + 1))
    connection.endheaders()
    response = connection.getresponse()
    assert response.status == 413
    response.read()
    connection.close()
    assert bridge._command_queue.empty()

    duplicate = http.client.HTTPConnection("127.0.0.1", port, timeout=2.0)
    duplicate.putrequest("POST", "/")
    duplicate.putheader("Content-Type", "application/json")
    duplicate.putheader("Authorization", f"Bearer {token}")
    duplicate.putheader("Authorization", "Bearer attacker")
    duplicate.putheader("Content-Length", "2")
    duplicate.endheaders(b"{}")
    duplicate_response = duplicate.getresponse()
    assert duplicate_response.status == 401
    duplicate_response.read()
    duplicate.close()
    assert bridge._command_queue.empty()


@pytest.mark.parametrize(("header", "first", "second", "expected"), (
    ("Authorization", "Bearer first", "Bearer second", 401),
    ("Host", "127.0.0.1:1", "127.0.0.1:2", 400),
    ("Content-Type", "application/json", "application/json", 415),
    ("Content-Length", "2", "2", 411),
))
def test_duplicate_critical_headers_fail_closed(
    bridge, header, first, second, expected
):
    port, token = _start(bridge)
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2.0)
    connection.putrequest(
        "POST",
        "/",
        skip_host=header == "Host",
        skip_accept_encoding=True,
    )
    if header != "Content-Type":
        connection.putheader("Content-Type", "application/json")
    if header != "Authorization":
        connection.putheader("Authorization", f"Bearer {token}")
    if header != "Content-Length":
        connection.putheader("Content-Length", "2")
    connection.putheader(header, first)
    connection.putheader(header, second)
    connection.endheaders(b"{}")
    response = connection.getresponse()
    assert response.status == expected
    response.read()
    connection.close()
    assert bridge._command_queue.empty()


def test_repeated_duplicate_content_length_returns_stable_411_and_stays_healthy(
    bridge, monkeypatch
):
    port, token = _start(bridge)
    dispatched = []
    original = bridge._execute_command

    def capture(command, params):
        dispatched.append(command)
        return original(command, params)

    monkeypatch.setattr(bridge, "_execute_command", capture)
    expected = {
        "success": False,
        "error": "A valid Content-Length is required",
    }

    for _ in range(25):
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2.0)
        connection.putrequest("POST", "/", skip_accept_encoding=True)
        connection.putheader("Content-Type", "application/json")
        connection.putheader("Authorization", f"Bearer {token}")
        connection.putheader("Content-Length", "2")
        connection.putheader("Content-Length", "2")
        connection.endheaders(b"{}")
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        connection.close()
        assert (response.status, payload) == (411, expected)

    assert dispatched == []
    assert bridge._command_queue.empty()

    status, payload, _ = _queued_response(bridge, port, token)
    assert status == 200
    assert payload["success"] is True
    assert dispatched == ["ping"]

    for credential in (None, "wrong" * 10):
        status, payload, _ = _response(port, token=credential)
        assert (status, payload) == (
            401,
            {"success": False, "error": "Authentication required"},
        )
    assert dispatched == ["ping"]
    assert bridge.get_status()["running"] is True


def test_signed_content_length_returns_411_without_dispatch_and_stays_healthy(
    bridge, monkeypatch
):
    port, token = _start(bridge)
    dispatched = []
    original = bridge._execute_command

    def capture(command, params):
        dispatched.append(command)
        return original(command, params)

    monkeypatch.setattr(bridge, "_execute_command", capture)
    body = b'{"command":"ping","params":{}}'
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2.0)
    connection.putrequest("POST", "/", skip_accept_encoding=True)
    connection.putheader("Content-Type", "application/json")
    connection.putheader("Authorization", f"Bearer {token}")
    connection.putheader("Content-Length", f"+{len(body)}")
    connection.endheaders(body)
    response = connection.getresponse()
    payload = json.loads(response.read().decode("utf-8"))
    connection.close()

    assert (response.status, payload) == (
        411,
        {"success": False, "error": "A valid Content-Length is required"},
    )
    assert dispatched == []
    assert bridge._command_queue.empty()

    status, payload, _ = _queued_response(bridge, port, token)
    assert status == 200
    assert payload["success"] is True
    assert dispatched == ["ping"]
    assert bridge.get_status()["running"] is True


def test_listener_executes_only_when_main_thread_tick_drains_queue(bridge, monkeypatch):
    port, token = _start(bridge)
    executed_on = []
    original = bridge._execute_command

    def capture(command, params):
        executed_on.append(threading.get_ident())
        return original(command, params)

    monkeypatch.setattr(bridge, "_execute_command", capture)
    completed: queue.Queue = queue.Queue()
    worker = threading.Thread(
        target=lambda: completed.put(_response(port, token=token)),
        daemon=True,
    )
    worker.start()
    deadline = time.time() + 2.0
    while bridge._command_queue.empty() and time.time() < deadline:
        time.sleep(0.01)
    assert not bridge._command_queue.empty()
    assert executed_on == []
    main_thread = threading.get_ident()
    bridge._tick(0.0)
    worker.join(timeout=2.0)
    assert completed.get_nowait()[0] == 200
    assert executed_on == [main_thread]
    assert bridge._dispatch_mode == "authenticated_queued"


def test_token_rotates_clears_and_never_enters_status_or_logs(bridge):
    first_port, first = _start(bridge)
    first_status = bridge.get_status()
    assert first_status["authenticated"] is True
    assert first_status["transport"] == "authenticated_queued"
    assert first not in json.dumps(first_status)
    assert first not in "\n".join(bridge._log_ring)
    assert first not in json.dumps(bridge.mcp_start(port=first_port))
    assert isinstance(bridge._c_get_log(200)["lines"], list)
    assert first not in json.dumps(bridge._c_get_log(200))

    handoff = bridge._token_handoff_path()
    assert handoff.exists()
    bridge.stop_listener()
    assert not handoff.exists()
    assert bridge._session_secret is None
    assert bridge.get_status()["transport"] == "unavailable"

    second_port = first_port if first_port else _free_port()
    bridge.start_listener(second_port)
    second = json.loads(handoff.read_text(encoding="utf-8"))["token"]
    assert second != first
    assert second not in json.dumps(bridge.get_status())
    assert second not in "\n".join(bridge._log_ring)


def test_active_secret_is_redacted_from_every_server_surface(bridge, monkeypatch):
    port, secret = _start(bridge)

    invalid_body = json.dumps({"command": secret, "params": {}}).encode()
    _status, invalid, _headers = _queued_response(
        bridge, port, secret, invalid_body
    )

    def fail_with_nested_secret(payload):
        raise RuntimeError(f"nested failure: {payload}")

    monkeypatch.setitem(bridge._HANDLERS, "synthetic_failure", fail_with_nested_secret)
    failure_body = json.dumps({
        "command": "synthetic_failure",
        "params": {"payload": {"tuple": [secret, f"prefix-{secret}-suffix"]}},
    }).encode()
    _status, failure, _headers = _queued_response(
        bridge, port, secret, failure_body
    )

    surfaces = {
        "invalid": invalid,
        "failure": failure,
        "logs": bridge._c_get_log(bridge.LOG_RING_SIZE),
        "history": bridge._c_history(bridge.HISTORY_CAP),
    }
    serialized = json.dumps(surfaces)
    assert secret not in serialized
    assert bridge._REDACTED in serialized
    assert secret not in "\n".join(bridge._log_ring)
    assert secret not in json.dumps(list(bridge._history))


def test_stop_rejects_pending_work_and_cleans_transport(bridge):
    port, token = _start(bridge)
    completed: queue.Queue = queue.Queue()
    worker = threading.Thread(
        target=lambda: completed.put(_response(port, token=token)),
        daemon=True,
    )
    worker.start()
    deadline = time.time() + 2.0
    while bridge._command_queue.empty() and time.time() < deadline:
        time.sleep(0.01)
    assert not bridge._command_queue.empty()

    handoff = bridge._token_handoff_path()
    bridge.stop_listener()
    worker.join(timeout=2.0)
    assert not worker.is_alive()
    status, payload, _ = completed.get_nowait()
    assert status == 200
    assert payload["success"] is False
    assert "stopped before command dispatch" in payload["error"]
    assert bridge._command_queue.empty()
    assert bridge._responses == {}
    assert bridge._server is None
    assert not handoff.exists()


def test_execute_python_is_unavailable_even_with_former_opt_in(bridge, monkeypatch):
    monkeypatch.setenv("UEFN_TOOLBELT_MCP_ALLOW_EXECUTE_PYTHON", "1")
    port, token = _start(bridge)
    status = bridge.get_status()
    assert status["execute_python_enabled"] is False
    assert "execute_python" not in bridge._public_commands()
    assert "execute_python" not in bridge._HANDLERS
    with pytest.raises(ValueError, match="Unknown command"):
        bridge._dispatch("execute_python", {"code": "result = 1"})

    body = json.dumps({
        "command": "execute_python",
        "params": {"code": "result = 1"},
    }).encode()
    http_status, payload, _ = _queued_response(bridge, port, token, body)
    assert http_status == 200
    assert payload["success"] is False
    assert "Unknown command" in payload["error"]


@pytest.mark.parametrize("tool_name", ("mcp_start", "mcp_stop", "mcp_restart"))
def test_listener_lifecycle_tools_are_local_only(bridge, tool_name):
    with pytest.raises(PermissionError, match="local-only"):
        bridge._c_run_tool(tool_name)


def test_integration_suite_is_local_only(bridge):
    with pytest.raises(PermissionError, match="local-only"):
        bridge._c_run_tool("toolbelt_integration_test")


@pytest.mark.parametrize("operation", ("start", "stop", "restart"))
def test_remote_dispatch_blocks_indirect_lifecycle_and_batch_bypass(
    bridge, monkeypatch, operation
):
    port, token = _start(bridge)

    def indirect_lifecycle():
        if operation == "start":
            bridge.start_listener(port)
        elif operation == "stop":
            bridge.stop_listener()
        else:
            bridge.restart_listener(port)
        return {"unexpected": True}

    command = f"synthetic_indirect_{operation}"
    monkeypatch.setitem(bridge._HANDLERS, command, indirect_lifecycle)

    direct = bridge._execute_command(command, {})
    assert direct["success"] is False
    assert "local-only" in direct["error"]
    assert bridge.get_status()["running"] is True
    assert json.loads(bridge._token_handoff_path().read_text(encoding="utf-8"))[
        "token"
    ] == token

    batched = bridge._execute_command("batch_exec", {"commands": [{
        "command": command,
        "params": {},
    }]})
    assert batched["success"] is True
    nested = batched["result"]["results"][0]
    assert nested["success"] is False
    assert "local-only" in nested["error"]
    assert bridge.get_status()["running"] is True
    assert json.loads(bridge._token_handoff_path().read_text(encoding="utf-8"))[
        "token"
    ] == token


def test_callback_registration_failure_leaves_no_listener_or_direct_mode(
    bridge, monkeypatch
):
    monkeypatch.setattr(
        bridge.unreal,
        "register_slate_post_tick_callback",
        lambda callback: (_ for _ in ()).throw(RuntimeError("Slate unavailable")),
    )
    token_file = bridge._token_handoff_path()
    token_file.write_text("stale credential", encoding="utf-8")
    with pytest.raises(RuntimeError, match="queued Slate dispatch"):
        bridge.start_listener(_free_port())
    assert bridge._server is None
    assert bridge._server_thread is None
    assert bridge._tick_handle is None
    assert bridge._session_secret is None
    assert bridge._dispatch_mode == "unavailable"
    assert not token_file.exists()


class _FakeFastMCP:
    def __init__(self, *args, **kwargs):
        self.tools = {}
        self.instructions = kwargs.get("instructions", "")

    def tool(self):
        def register(function):
            self.tools[function.__name__] = function
            return function
        return register

    def run(self):  # pragma: no cover - entry point is never invoked in tests
        raise AssertionError("FastMCP.run() must not run during unit tests")


def _load_external_client(repo_root, tmp_path, monkeypatch, token: str):
    fastmcp = types.ModuleType("mcp.server.fastmcp")
    fastmcp.FastMCP = _FakeFastMCP
    server = types.ModuleType("mcp.server")
    mcp_package = types.ModuleType("mcp")
    monkeypatch.setitem(sys.modules, "mcp", mcp_package)
    monkeypatch.setitem(sys.modules, "mcp.server", server)
    monkeypatch.setitem(sys.modules, "mcp.server.fastmcp", fastmcp)
    handoff = tmp_path / "external_session.json"
    handoff.write_text(
        json.dumps({
            "version": 1,
            "host": "127.0.0.1",
            "port": 8765,
            "token": token,
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("UEFN_MCP_TOKEN_FILE", str(handoff))
    spec = importlib.util.spec_from_file_location(
        "mcp_server_security_case",
        repo_root / "mcp_server.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, handoff


def test_external_client_authenticates_without_exposing_token(
    repo_root, tmp_path, monkeypatch
):
    token = "s" * 43
    monkeypatch.setenv("UEFN_TOOLBELT_MCP_ALLOW_EXECUTE_PYTHON", "1")
    client, handoff = _load_external_client(repo_root, tmp_path, monkeypatch, token)
    captured = {}

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"success":true,"result":{"status":"ok"}}'

    def success(request, timeout):
        captured["authorization"] = request.get_header("Authorization")
        return Response()

    # The transport seam is the per-request direct opener (WO-004 Session B).
    monkeypatch.setattr(client, "_direct_opener", lambda: _Opener(success))
    assert client._send("ping") == {"status": "ok"}
    assert captured["authorization"] == f"Bearer {token}"
    assert "execute_python" not in client.mcp.tools

    rotated = "r" * 43
    handoff.write_text(
        json.dumps({
            "version": 1,
            "host": "127.0.0.1",
            "port": 8765,
            "token": rotated,
        }),
        encoding="utf-8",
    )
    assert client._send("ping") == {"status": "ok"}
    assert captured["authorization"] == f"Bearer {rotated}"

    def unauthorized(request, timeout):
        # The bridge's own 401 carries its exact rejection body; a bodiless
        # 401 is an unknown outcome under Session B, not a rejection.
        raise urllib.error.HTTPError(
            request.full_url, 401, "Unauthorized", {},
            io.BytesIO(_BRIDGE_401_BODY),
        )

    monkeypatch.setattr(client, "_direct_opener", lambda: _Opener(unauthorized))
    with pytest.raises(PermissionError) as exc_info:
        client._send("ping")
    for secret in (token, rotated):
        assert secret not in str(exc_info.value)
        assert secret not in repr(exc_info.value)

    class ReflectedFailure(Response):
        def read(self):
            return json.dumps({
                "success": False,
                "error": f"failure {rotated}",
                "traceback": {"nested": [rotated]},
            }).encode()

    monkeypatch.setattr(
        client,
        "_direct_opener",
        lambda: _Opener(lambda request, timeout: ReflectedFailure()),
    )
    with pytest.raises(RuntimeError) as reflected:
        client._send(rotated)
    assert rotated not in str(reflected.value)
    assert "[REDACTED]" in str(reflected.value)


def test_stdlib_client_uses_handoff_and_keeps_execute_python_off(
    repo_root, tmp_path, monkeypatch
):
    spec = importlib.util.spec_from_file_location(
        "toolbelt_stdlib_client_security_case",
        repo_root / "client.py",
    )
    assert spec is not None and spec.loader is not None
    client_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(client_module)

    token = "t" * 43
    handoff = tmp_path / "client_session.json"
    handoff.write_text(
        json.dumps({
            "version": 1,
            "host": "127.0.0.1",
            "port": 8765,
            "token": token,
        }),
        encoding="utf-8",
    )
    client = client_module.ToolbeltClient(token_file=handoff)
    captured = {}

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"success":true,"result":{"status":"ok"}}'

    def success(request, timeout):
        captured["authorization"] = request.get_header("Authorization")
        return Response()

    # The transport seam is the per-request direct opener (WO-004 Session B).
    monkeypatch.setattr(client_module, "_direct_opener", lambda: _Opener(success))
    assert client.ping() == {"status": "ok"}
    assert captured["authorization"] == f"Bearer {token}"

    monkeypatch.setenv("UEFN_TOOLBELT_MCP_ALLOW_EXECUTE_PYTHON", "1")
    with pytest.raises(client_module.ToolbeltError, match="unavailable"):
        client.execute_python("result = 1")

    class ReflectedFailure(Response):
        def read(self):
            return json.dumps({
                "success": False,
                "error": token,
                "traceback": {"nested": [f"prefix-{token}"]},
            }).encode()

    monkeypatch.setattr(
        client_module,
        "_direct_opener",
        lambda: _Opener(lambda request, timeout: ReflectedFailure()),
    )
    with pytest.raises(client_module.ToolbeltError) as reflected:
        client._send(token)
    assert token not in str(reflected.value)
    assert "[REDACTED]" in str(reflected.value)

    def unauthorized(request, timeout):
        # The bridge's own 401 carries its exact rejection body; a bodiless
        # 401 is an unknown outcome under Session B, not a rejection.
        raise urllib.error.HTTPError(
            request.full_url, 401, "Unauthorized", {},
            io.BytesIO(_BRIDGE_401_BODY),
        )

    monkeypatch.setattr(client_module, "_direct_opener", lambda: _Opener(unauthorized))
    with pytest.raises(client_module.AuthenticationError) as exc_info:
        client.ping()
    assert token not in str(exc_info.value)
    assert token not in repr(exc_info.value)


# --- WO-004 Session B: client outcome semantics -----------------------------
#
# The static verification the issued WO-004 mandate prescribes for both
# clients. Every test uses a dummy token and a synthetic handoff, and drives
# either the per-request opener seam or isolated fake servers on ephemeral
# loopback ports. None reads a live handoff, uses a live token, or reaches a
# real proxy. Proving what a running editor produces is Session C's job.

_DUMMY_TOKEN = "dummy-session-token-for-outcome-tests-" + "x" * 10
_BRIDGE_401_BODY = b'{"success": false, "error": "Authentication required"}'
_BRIDGE_SOURCE = (
    Path(__file__).resolve().parents[1] / "Content" / "Python"
    / "UEFN_Toolbelt" / "tools" / "mcp_bridge.py"
)
_STOP_DRAIN = "MCP listener stopped before command dispatch"
_COMMAND = "set_viewport_camera"
# The command carries the dummy token, so every row also proves redaction.
_SENT = _COMMAND + "-" + _DUMMY_TOKEN
_UNKNOWN_PHRASES = (
    "may not have run",
    "may still be queued or running",
    "may have completed",
    "until that state has been checked",
    "can also go unanswered",
    "cannot determine why no reply arrived",
    "UEFN editor",
)
_FORBIDDEN_IN_UNKNOWN = (
    "modal", "dialog", "blocked", "heavy operation", "shorter operation",
    "retry", "rejected", "refused", "not running",
)


class _Opener:
    """Stands in for the per-request direct opener and records each attempt."""

    def __init__(self, respond):
        self.respond = respond
        self.attempts: list = []

    def open(self, request, timeout=None):
        self.attempts.append(request)
        return self.respond(request, timeout)


class _Reply:
    """A 2xx response as urllib returns it: status, then a readable body."""

    def __init__(self, status: int, body):
        self.status = status
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        if isinstance(self._body, BaseException):
            raise self._body
        return self._body


def _respond_with(factory):
    def respond(request, timeout):
        outcome = factory()
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome
    return respond


def _http_error(code: int, body: bytes | None) -> urllib.error.HTTPError:
    fp = None if body is None else io.BytesIO(body)
    return urllib.error.HTTPError("http://127.0.0.1:8765/", code, "status", {}, fp)


def _envelope(error: str, **extra) -> bytes:
    return json.dumps({"success": False, "error": error, **extra}).encode()


def _bridge_rejection_pairs() -> set[tuple[int, str]]:
    """Every literal (status, error) the bridge passes to _reject or _error."""
    tree = ast.parse(_BRIDGE_SOURCE.read_text(encoding="utf-8"))
    pairs = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("_reject", "_error")
            and len(node.args) >= 2
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, int)
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            pairs.add((node.args[0].value, node.args[1].value))
    return pairs


def _bridge_deadline_prefixes() -> list[str]:
    """The literal prefix of every 504 body the bridge formats."""
    tree = ast.parse(_BRIDGE_SOURCE.read_text(encoding="utf-8"))
    prefixes = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "_error"
            and len(node.args) >= 2
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == 504
            and isinstance(node.args[1], ast.JoinedStr)
            and isinstance(node.args[1].values[0], ast.Constant)
        ):
            prefixes.append(node.args[1].values[0].value)
    return prefixes


def _stdlib_client_module(repo_root):
    spec = importlib.util.spec_from_file_location(
        "toolbelt_client_outcome_case", repo_root / "client.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_handoff(path, port: int = 8765, token: str = _DUMMY_TOKEN):
    path.write_text(json.dumps({
        "version": 1, "host": "127.0.0.1", "port": port, "token": token,
    }), encoding="utf-8")
    return path


def _sender(kind, repo_root, tmp_path, monkeypatch, *, port: int = 8765,
            handoff: str = "valid"):
    """(module, send) for one client, wired to a synthetic handoff.

    `handoff` is "valid", "missing", or "invalid" (a too-short token).
    """
    token = _DUMMY_TOKEN if handoff != "invalid" else "short"
    if kind == "client":
        module = _stdlib_client_module(repo_root)
        path = tmp_path / "client_outcome_handoff.json"
        if handoff != "missing":
            _write_handoff(path, port, token)
        return module, module.ToolbeltClient(token_file=path)._send
    module, path = _load_external_client(
        repo_root, tmp_path, monkeypatch, _DUMMY_TOKEN
    )
    if handoff == "missing":
        path.unlink()
    else:
        _write_handoff(path, port, token)
    return module, module._send


def _expected(kind, module, name):
    return getattr(module, name) if kind == "client" else getattr(builtins, name)


_KINDS = ("client", "server")

# (id, outcome factory, client.py class, mcp_server.py class, message group)
_OUTCOME_ROWS = [
    ("refused",
     lambda: urllib.error.URLError(ConnectionRefusedError(10061, "refused")),
     "NotConnected", "ConnectionError", "refused"),
    ("timeout-direct", lambda: TimeoutError("timed out"),
     "CommandTimeout", "TimeoutError", "unknown"),
    ("timeout-wrapped",
     lambda: urllib.error.URLError(TimeoutError("timed out")),
     "CommandTimeout", "TimeoutError", "unknown"),
    ("504-bridge-deadline",
     lambda: _http_error(504, _envelope("Command timed out: " + _SENT)),
     "CommandTimeout", "TimeoutError", "unknown"),
    ("504-other-command",
     lambda: _http_error(504, _envelope("Command timed out: ping")),
     "OutcomeUnknown", "RuntimeError", "unknown"),
    ("504-without-body", lambda: _http_error(504, None),
     "OutcomeUnknown", "RuntimeError", "unknown"),
    ("401-without-body", lambda: _http_error(401, None),
     "OutcomeUnknown", "RuntimeError", "unknown"),
    ("401-extra-key",
     lambda: _http_error(401, _envelope("Authentication required",
                                        traceback="")),
     "OutcomeUnknown", "RuntimeError", "unknown"),
    ("301", lambda: _http_error(301, b"moved"),
     "OutcomeUnknown", "RuntimeError", "unknown"),
    ("302", lambda: _http_error(302, b"found"),
     "OutcomeUnknown", "RuntimeError", "unknown"),
    ("303", lambda: _http_error(303, b"see other"),
     "OutcomeUnknown", "RuntimeError", "unknown"),
    ("502", lambda: _http_error(502, b"<html>bad gateway</html>"),
     "OutcomeUnknown", "RuntimeError", "unknown"),
    ("203-success", lambda: _Reply(203, b'{"success": true, "result": 1}'),
     "OutcomeUnknown", "RuntimeError", "unknown"),
    ("remote-disconnected", lambda: http.client.RemoteDisconnected("closed"),
     "OutcomeUnknown", "RuntimeError", "unknown"),
    ("connection-reset", lambda: ConnectionResetError(10054, "reset"),
     "OutcomeUnknown", "RuntimeError", "unknown"),
    ("connection-reset-wrapped",
     lambda: urllib.error.URLError(ConnectionResetError(10054, "reset")),
     "OutcomeUnknown", "ConnectionError", "unknown"),
    ("other-url-error", lambda: urllib.error.URLError(OSError("unreachable")),
     "OutcomeUnknown", "ConnectionError", "unknown"),
    # A refusal is recognized by the reason's type only, never by its text.
    ("url-error-text-mentions-refusal",
     lambda: urllib.error.URLError(OSError(
         "No connection could be made because the target machine actively"
         " refused it")),
     "OutcomeUnknown", "ConnectionError", "unknown"),
    ("200-truncated",
     lambda: _Reply(200, http.client.IncompleteRead(b'{"succ', 20)),
     "OutcomeUnknown", "RuntimeError", "unknown"),
    ("200-non-json", lambda: _Reply(200, b"<html>ok</html>"),
     "OutcomeUnknown", "RuntimeError", "unknown"),
    ("200-non-object", lambda: _Reply(200, b"[1, 2, 3]"),
     "OutcomeUnknown", "RuntimeError", "unknown"),
    ("200-truthy-non-boolean",
     lambda: _Reply(200, b'{"success": "yes", "result": 1}'),
     "OutcomeUnknown", "RuntimeError", "unknown"),
    ("200-stop-drain", lambda: _Reply(200, _envelope(_STOP_DRAIN)),
     "ToolbeltError", "RuntimeError", "drained"),
    ("200-stop-drain-with-traceback",
     lambda: _Reply(200, _envelope(_STOP_DRAIN, traceback="Traceback ...")),
     "ToolbeltError", "RuntimeError", "failure"),
    ("200-reported-failure",
     lambda: _Reply(200, _envelope("failure " + _DUMMY_TOKEN,
                                   traceback="tb " + _DUMMY_TOKEN)),
     "ToolbeltError", "RuntimeError", "failure"),
]
for _code, _error in sorted(_bridge_rejection_pairs()):
    _OUTCOME_ROWS.append((
        "rejected-" + str(_code) + "-" + _error,
        (lambda code=_code, error=_error: _http_error(code, _envelope(error))),
        "AuthenticationError" if _code == 401 else "ToolbeltError",
        "PermissionError" if _code == 401 else "RuntimeError",
        "rejected",
    ))
for _code in sorted({code for code, _error in _bridge_rejection_pairs()}):
    _OUTCOME_ROWS.append((
        "status-" + str(_code) + "-other-body",
        (lambda code=_code: _http_error(code, _envelope("some other error"))),
        "OutcomeUnknown", "RuntimeError", "unknown",
    ))


@pytest.mark.parametrize("kind", _KINDS)
@pytest.mark.parametrize(("name", "factory", "client_cls", "server_cls", "group"),
                         _OUTCOME_ROWS, ids=[row[0] for row in _OUTCOME_ROWS])
def test_outcome_classification_follows_the_mandate(
    repo_root, tmp_path, monkeypatch, kind, name, factory, client_cls,
    server_cls, group
):
    """Each response raises its class after exactly one attempt, redacted.

    Static verification items 1, 3, 7, and 9 of the issued WO-004 mandate.
    """
    module, send = _sender(kind, repo_root, tmp_path, monkeypatch)
    opener = _Opener(_respond_with(factory))
    monkeypatch.setattr(module, "_direct_opener", lambda: opener)
    expected = _expected(kind, module, client_cls if kind == "client"
                         else server_cls)

    with pytest.raises(expected) as exc_info:
        send(_SENT)

    error = exc_info.value
    assert type(error) is expected, name + ": raised " + type(error).__name__
    assert len(opener.attempts) == 1, name + ": attempts " + str(len(opener.attempts))
    message = str(error)
    assert _DUMMY_TOKEN not in message
    assert _DUMMY_TOKEN not in repr(error)
    lowered = message.lower()
    if group == "unknown":
        assert _COMMAND in message
        for phrase in _UNKNOWN_PHRASES:
            assert phrase in message, name + ": missing " + repr(phrase)
        for word in _FORBIDDEN_IN_UNKNOWN:
            assert word not in lowered, name + ": names " + repr(word)
    else:
        assert "may not have run" not in message
    if group == "refused":
        assert "no request reached" in message
    if group == "rejected":
        assert "rejected the request before queueing it" in message
    else:
        assert "reject" not in lowered, name + ": rejection wording"
    if group == "drained":
        assert "stopped before it dispatched" in message
    if group == "failure":
        assert "may have failed before running or partway through" in message
        for claim in ("did not run", "was not executed", "was executed",
                      "has run"):
            assert claim not in lowered


@pytest.mark.parametrize("kind", _KINDS)
def test_a_bridge_result_is_returned_after_one_attempt(
    repo_root, tmp_path, monkeypatch, kind
):
    """Row 7: a 200 whose body is an object with success true."""
    module, send = _sender(kind, repo_root, tmp_path, monkeypatch)
    opener = _Opener(_respond_with(
        lambda: _Reply(200, b'{"success": true, "result": {"ok": 1}}')))
    monkeypatch.setattr(module, "_direct_opener", lambda: opener)
    assert send("ping") == {"ok": 1}
    assert len(opener.attempts) == 1


@pytest.mark.parametrize("kind", _KINDS)
@pytest.mark.parametrize("handoff", ("missing", "invalid"))
def test_no_request_is_attempted_without_a_valid_handoff(
    repo_root, tmp_path, monkeypatch, kind, handoff
):
    """Row 1: zero attempts, and the message says no request was sent."""
    module, send = _sender(kind, repo_root, tmp_path, monkeypatch,
                           handoff=handoff)
    opener = _Opener(_respond_with(lambda: AssertionError("no attempt")))
    monkeypatch.setattr(module, "_direct_opener", lambda: opener)
    expected = _expected(kind, module, "AuthenticationError" if kind == "client"
                         else "ConnectionError")

    with pytest.raises(expected) as exc_info:
        send(_COMMAND)

    assert type(exc_info.value) is expected
    assert opener.attempts == []
    assert "No request was sent" in str(exc_info.value)
    assert "may not have run" not in str(exc_info.value)


class _PreThreeTenTimeout(OSError):
    """socket.timeout as it was before Python 3.10: an OSError, not TimeoutError."""


@pytest.mark.parametrize("kind", _KINDS)
@pytest.mark.parametrize("wrapped", (False, True), ids=("direct", "wrapped"))
def test_a_distinct_socket_timeout_type_is_still_a_timeout(
    repo_root, tmp_path, monkeypatch, kind, wrapped
):
    """Row 3 holds where socket.timeout is not TimeoutError (Python < 3.10).

    This simulates that relationship on the running interpreter; it does not
    prove execution on an untested Python version.
    """
    assert not issubclass(_PreThreeTenTimeout, TimeoutError)
    monkeypatch.setattr(socket, "timeout", _PreThreeTenTimeout)
    module, send = _sender(kind, repo_root, tmp_path, monkeypatch)

    def factory():
        error = _PreThreeTenTimeout("timed out")
        return urllib.error.URLError(error) if wrapped else error

    opener = _Opener(_respond_with(factory))
    monkeypatch.setattr(module, "_direct_opener", lambda: opener)
    expected = _expected(kind, module, "CommandTimeout" if kind == "client"
                         else "TimeoutError")

    with pytest.raises(expected) as exc_info:
        send(_COMMAND)

    assert type(exc_info.value) is expected
    assert len(opener.attempts) == 1


@pytest.mark.parametrize("kind", _KINDS)
def test_known_bridge_responses_match_the_bridge_source(
    repo_root, tmp_path, monkeypatch, kind
):
    """Static verification item 2: a bridge message change fails here.

    The clients' enumerated rejections equal the bridge's literal _reject and
    _error pairs; the 504 deadline prefix and the stop-drain error match the
    bridge's own text.
    """
    module, _send = _sender(kind, repo_root, tmp_path, monkeypatch)
    bridge_pairs = _bridge_rejection_pairs()
    assert len(bridge_pairs) >= 14
    assert bridge_pairs == module._BRIDGE_REJECTIONS
    assert _bridge_deadline_prefixes() == [module._DEADLINE_ERROR_PREFIX]
    assert (
        '"error": "' + module._STOP_DRAIN_ERROR + '"'
        in _BRIDGE_SOURCE.read_text(encoding="utf-8")
    )


def _counting_real_opener(module, monkeypatch):
    """Wrap the production opener so each real attempt is recorded."""
    real = module._direct_opener
    attempts: list = []

    def counting():
        opener = real()
        original = opener.open

        def open_(request, *args, **kwargs):
            attempts.append(request.full_url)
            return original(request, *args, **kwargs)

        opener.open = open_
        return opener

    monkeypatch.setattr(module, "_direct_opener", counting)
    return attempts


def _fake_server(status: int, body: bytes, headers: dict | None = None):
    """A loopback HTTP server that records every request it receives."""
    seen: list = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def _handle(self):
            length = int(self.headers.get("Content-Length") or 0)
            payload = self.rfile.read(length) if length else b""
            seen.append({
                "line": self.requestline,
                "authorization": self.headers.get("Authorization"),
                "body": payload,
            })
            self.send_response(status)
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = do_POST = _handle

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, seen


class _RawListener:
    """A loopback TCP listener that records any connection and any bytes."""

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.sock.settimeout(0.1)
        self.port = int(self.sock.getsockname()[1])
        self.accepted = 0
        self.received = b""
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            try:
                connection, _address = self.sock.accept()
            except OSError:
                continue
            self.accepted += 1
            connection.settimeout(0.5)
            try:
                self.received += connection.recv(65536)
            except OSError:
                pass
            connection.close()

    def close(self):
        self._stop.set()
        self._thread.join(timeout=2.0)
        self.sock.close()


@pytest.mark.parametrize("kind", _KINDS)
def test_a_refused_connection_delivers_nothing(
    repo_root, tmp_path, monkeypatch, kind
):
    """Static verification item 4, on the real opener and a closed port."""
    module, send = _sender(kind, repo_root, tmp_path, monkeypatch,
                           port=_free_port())
    attempts = _counting_real_opener(module, monkeypatch)
    expected = _expected(kind, module, "NotConnected" if kind == "client"
                         else "ConnectionError")

    with pytest.raises(expected) as exc_info:
        send(_COMMAND)

    assert type(exc_info.value) is expected
    assert len(attempts) == 1
    assert "no request reached" in str(exc_info.value)
    assert "may not have run" not in str(exc_info.value)


@pytest.mark.parametrize("kind", _KINDS)
def test_environment_proxies_are_bypassed(
    repo_root, tmp_path, monkeypatch, kind
):
    """Static verification item 5: the fake proxy sees no connection."""
    endpoint, seen = _fake_server(
        200, b'{"success": true, "result": {"via": "endpoint"}}')
    proxy = _RawListener()
    try:
        module, send = _sender(kind, repo_root, tmp_path, monkeypatch,
                               port=endpoint.server_address[1])
        proxy_url = "http://127.0.0.1:" + str(proxy.port)
        for name in ("HTTP_PROXY", "http_proxy", "ALL_PROXY"):
            monkeypatch.setenv(name, proxy_url)
        for name in ("NO_PROXY", "no_proxy"):
            monkeypatch.delenv(name, raising=False)
        # Non-vacuous: urllib's default handling would route through it.
        assert urllib.request.getproxies().get("http") == proxy_url
        environment = dict(os.environ)
        global_opener = urllib.request._opener

        assert send("ping") == {"via": "endpoint"}

        assert dict(os.environ) == environment
        assert urllib.request._opener is global_opener
        assert len(seen) == 1
        assert seen[0]["authorization"] == "Bearer " + _DUMMY_TOKEN
        assert proxy.accepted == 0
        assert _DUMMY_TOKEN.encode() not in proxy.received
    finally:
        proxy.close()
        endpoint.shutdown()
        endpoint.server_close()


@pytest.mark.parametrize("kind", _KINDS)
def test_a_redirect_is_not_followed(repo_root, tmp_path, monkeypatch, kind):
    """Static verification item 6: one attempt, and the target sees nothing."""
    target, target_seen = _fake_server(
        200, b'{"success": true, "result": {"via": "redirect"}}')
    first, first_seen = _fake_server(302, b"", {
        "Location": "http://127.0.0.1:" + str(target.server_address[1])
                    + "/elsewhere",
    })
    try:
        module, send = _sender(kind, repo_root, tmp_path, monkeypatch,
                               port=first.server_address[1])
        attempts = _counting_real_opener(module, monkeypatch)
        expected = _expected(kind, module, "OutcomeUnknown" if kind == "client"
                             else "RuntimeError")

        with pytest.raises(expected) as exc_info:
            send(_COMMAND)

        assert type(exc_info.value) is expected
        assert len(attempts) == 1
        assert len(first_seen) == 1
        assert target_seen == []
        assert "may not have run" in str(exc_info.value)
    finally:
        for server in (first, target):
            server.shutdown()
            server.server_close()


@pytest.mark.parametrize("kind", _KINDS)
def test_the_production_opener_is_direct_and_per_request(
    repo_root, tmp_path, monkeypatch, kind
):
    """No proxy handler at all, and no redirect handler that follows.

    ProxyHandler({}) registers no protocol method, so the opener does not
    keep it; passing it only stops build_opener adding the default handler
    that reads environment and system proxies.
    """
    module, _send = _sender(kind, repo_root, tmp_path, monkeypatch)
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    opener = module._direct_opener()
    assert opener is not module._direct_opener()
    assert not [handler for handler in opener.handlers
                if isinstance(handler, urllib.request.ProxyHandler)]
    default = urllib.request.build_opener()
    assert [handler for handler in default.handlers
            if isinstance(handler, urllib.request.ProxyHandler)], (
        "control: with a proxy configured, urllib's default opener keeps one"
    )
    redirects = [handler for handler in opener.handlers
                 if isinstance(handler, urllib.request.HTTPRedirectHandler)]
    assert len(redirects) == 1
    assert type(redirects[0]) is module._RefuseRedirects


def test_connect_sends_a_single_ping(repo_root, tmp_path, monkeypatch):
    module = _stdlib_client_module(repo_root)
    monkeypatch.setenv("UEFN_MCP_TOKEN_FILE",
                       str(_write_handoff(tmp_path / "connect_handoff.json")))
    opener = _Opener(_respond_with(
        lambda: _Reply(200, b'{"success": true, "result": {"status": "ok"}}')))
    monkeypatch.setattr(module, "_direct_opener", lambda: opener)
    module.connect()
    assert len(opener.attempts) == 1


def test_outcome_unknown_sits_inside_the_existing_hierarchy(repo_root):
    module = _stdlib_client_module(repo_root)
    assert issubclass(module.OutcomeUnknown, module.ToolbeltError)
    assert issubclass(module.CommandTimeout, module.OutcomeUnknown)
    assert not issubclass(module.NotConnected, module.OutcomeUnknown)
    assert not issubclass(module.AuthenticationError, module.OutcomeUnknown)


def test_agent_instructions_explain_unknown_outcomes(
    repo_root, tmp_path, monkeypatch
):
    """Static verification item 8."""
    module, _handoff = _load_external_client(
        repo_root, tmp_path, monkeypatch, _DUMMY_TOKEN)
    instructions = module.mcp.instructions
    for phrase in (
        "a timeout, a lost connection, or an unexpected response",
        "Do not automatically send a state-changing tool call again",
        "inspect state with read tools before deciding",
        "get_history entries carry a command name, an elapsed time, and a "
        "success flag",
        "cannot identify a specific call or show how many times it ran",
    ):
        assert phrase in instructions, phrase
    lowered = instructions.lower()
    assert "modal" not in lowered
    assert "dialog" not in lowered


# --- Session B review follow-ups: three discriminating regression families --


class _StallingBody:
    """An HTTP error body whose read times out, as a stalled socket would."""

    def read(self, *args):
        raise TimeoutError("timed out")

    def readline(self, *args):
        raise TimeoutError("timed out")

    def close(self):
        pass


@pytest.mark.parametrize("kind", _KINDS)
@pytest.mark.parametrize("code", (504, 401, 502))
def test_a_timeout_reading_an_error_body_is_a_timeout(
    repo_root, tmp_path, monkeypatch, kind, code
):
    """Row 3 still precedes rows 4 to 6 when the error body's read times out."""
    module, send = _sender(kind, repo_root, tmp_path, monkeypatch)
    opener = _Opener(_respond_with(lambda: urllib.error.HTTPError(
        "http://127.0.0.1:8765/", code, "status", {}, _StallingBody())))
    monkeypatch.setattr(module, "_direct_opener", lambda: opener)
    expected = _expected(kind, module, "CommandTimeout" if kind == "client"
                         else "TimeoutError")

    with pytest.raises(expected) as exc_info:
        send(_SENT)

    error = exc_info.value
    assert type(error) is expected
    assert len(opener.attempts) == 1
    assert error.__suppress_context__ is True
    message = str(error)
    for phrase in _UNKNOWN_PHRASES:
        assert phrase in message
    assert _DUMMY_TOKEN not in message
    assert _DUMMY_TOKEN not in repr(error)


# A known rejection or deadline body requires success to be exactly the
# boolean false. A numeric 0 compares equal to False but is not the bridge's
# envelope, so the reply stays an unknown outcome.
_NUMERIC_FALSE_BODIES = (
    ("401-success-zero", 401, {"success": 0, "error": "Authentication required"}),
    ("400-success-zero", 400, {"success": 0, "error": "Malformed JSON request"}),
    ("504-success-zero", 504, {"success": 0, "error": "Command timed out: " + _SENT}),
)


@pytest.mark.parametrize("kind", _KINDS)
@pytest.mark.parametrize(("name", "code", "body"), _NUMERIC_FALSE_BODIES,
                         ids=[row[0] for row in _NUMERIC_FALSE_BODIES])
def test_numeric_false_is_not_the_bridge_envelope(
    repo_root, tmp_path, monkeypatch, kind, name, code, body
):
    module, send = _sender(kind, repo_root, tmp_path, monkeypatch)
    opener = _Opener(_respond_with(
        lambda: _http_error(code, json.dumps(body).encode())))
    monkeypatch.setattr(module, "_direct_opener", lambda: opener)
    expected = _expected(kind, module, "OutcomeUnknown" if kind == "client"
                         else "RuntimeError")

    with pytest.raises(expected) as exc_info:
        send(_SENT)

    assert type(exc_info.value) is expected, (
        name + ": " + type(exc_info.value).__name__)
    assert len(opener.attempts) == 1
    assert "may not have run" in str(exc_info.value)
    assert "reject" not in str(exc_info.value).lower()


# Unknown outcomes raised while a transport exception is being handled
# suppress that exception's context, so its text - which can repeat request
# details - never travels with the client's error.
_CONTEXT_ROW_IDS = (
    "timeout-direct", "timeout-wrapped", "504-bridge-deadline",
    "504-without-body", "401-without-body", "502", "remote-disconnected",
    "connection-reset", "connection-reset-wrapped", "other-url-error",
    "url-error-text-mentions-refusal",
)
_CONTEXT_ROWS = [row for row in _OUTCOME_ROWS if row[0] in _CONTEXT_ROW_IDS]
assert len(_CONTEXT_ROWS) == len(_CONTEXT_ROW_IDS)


@pytest.mark.parametrize("kind", _KINDS)
@pytest.mark.parametrize(("name", "factory", "client_cls", "server_cls", "group"),
                         _CONTEXT_ROWS, ids=[row[0] for row in _CONTEXT_ROWS])
def test_unknown_outcomes_suppress_the_transport_exception_context(
    repo_root, tmp_path, monkeypatch, kind, name, factory, client_cls,
    server_cls, group
):
    module, send = _sender(kind, repo_root, tmp_path, monkeypatch)
    monkeypatch.setattr(module, "_direct_opener",
                        lambda: _Opener(_respond_with(factory)))
    expected = _expected(kind, module, client_cls if kind == "client"
                         else server_cls)

    with pytest.raises(expected) as exc_info:
        send(_SENT)

    error = exc_info.value
    assert "may not have run" in str(error)
    assert error.__cause__ is None
    assert error.__suppress_context__ is True, (
        name + ": the transport exception's context is not suppressed")


# --- WO-008 oversized-reply correction: paged MCP listings --------------------
#
# list_toolbelt_tools and get_all_actors return one bounded page per call
# (proposal r5, tests 1-12). Every test loads mcp_server.py through
# _FakeFastMCP, which registers the raw function with no argument model, and
# stubs _send. They show what the functions do with the values they receive,
# not how an MCP SDK coerces arguments first, and they prove nothing about any
# client's output limit.

_PAGED_OTHER_TOOLS = frozenset({
    "ping", "mcp_get_log", "run_toolbelt_tool", "describe_toolbelt_tool",
    "get_selected_actors", "spawn_actor", "delete_actors", "set_actor_transform",
    "set_actor_property", "get_actor_properties", "list_assets", "get_asset_info",
    "get_selected_assets", "rename_asset", "delete_asset", "duplicate_asset",
    "does_asset_exist", "save_asset", "import_asset", "search_assets",
    "create_material_instance", "batch_exec", "undo", "redo", "get_history",
    "save_current_level", "get_level_info", "get_viewport_camera",
    "set_viewport_camera", "verse_book_search", "verse_book_chapter",
    "verse_book_update",
})
_SUMMARY_KEYS = ["name", "category", "description", "tags"]


def _paged_tool(i: int, **override) -> dict:
    """One registry entry, in the field order registry.list_tools() writes."""
    entry = {
        "name": f"tool_{i:03d}", "category": f"Category {i % 55:02d}",
        "description": f"Description of tool {i}. " * 3, "icon": "*",
        "shortcut": "", "tags": [f"tag{i % 7}"], "source": "core",
        "author": "Ocean Bennett", "version": "1.0", "url": "",
        "last_updated": "2026-10-01",
    }
    entry.update(override)
    return entry


def _paged_actor(i: int, **override) -> dict:
    """One actor, in the field order the bridge's _serialize_actor writes."""
    entry = {
        "name": f"A_{i:05d}", "label": f"Label_{i:05d}", "class": "StaticMeshActor",
        "path": f"/P/P.P:PersistentLevel.Actor_UAX_{i:05d}",
        "location": {"x": float(i), "y": 2.5 * i, "z": 10.0},
        "rotation": {"pitch": 0.0, "yaw": float(i % 360), "roll": 0.0},
        "scale": {"x": 1.0, "y": 1.0, "z": 1.0},
    }
    entry.update(override)
    return entry


def _shuffled(entries: list, seed: int) -> list:
    out = list(entries)
    random.Random(seed).shuffle(out)
    return out


_PAGED_TOOLS = _shuffled([_paged_tool(i) for i in range(362)], 362)
_PAGED_ACTORS = {n: _shuffled([_paged_actor(i) for i in range(n)], n) for n in (0, 1, 176, 2000)}


def _paged(repo_root, tmp_path, monkeypatch, *, tools=None, actors=None, script=None):
    """(module, calls): mcp_server.py with _send replaced by a recording stub.

    `script(command, params, call_number)` overrides the fixed listings, so a
    test can change the bridge's answer between page calls.
    """
    module, _handoff = _load_external_client(repo_root, tmp_path, monkeypatch, _DUMMY_TOKEN)
    calls: list = []

    def send(command, params=None, timeout=None):
        calls.append((command, copy.deepcopy(params)))
        if script is not None:
            return script(command, params, len(calls))
        if command == "list_tools":
            return {"tools": tools, "count": len(tools)}
        if command == "get_all_actors":
            return {"actors": actors, "count": len(actors)}
        raise AssertionError("unexpected bridge command " + command)

    monkeypatch.setattr(module, "_send", send)
    return module, calls


def _page(reply: str) -> tuple[str | None, dict]:
    """(first line or None, the parsed page object)."""
    if reply.startswith("// "):
        first, rest = reply.split("\n", 1)
        return first, json.loads(rest)
    return None, json.loads(reply)


def _walk(tool, step_bound: int = 5000, **kwargs) -> list[str]:
    """Follow next_offset from 0; fail the test if the walk does not end."""
    replies, offset = [], 0
    for _ in range(step_bound):
        reply = tool(offset=offset, **kwargs)
        replies.append(reply)
        body = _page(reply)[1]
        if body["next_offset"] is None:
            return replies
        offset = body["next_offset"]
    raise AssertionError(f"the walk did not reach complete within {step_bound} pages")


def _expected_sha(text: str) -> str:
    """The §3.5 hash form, computed here independently of mcp_server.py."""
    return "sha256:" + hashlib.sha256(text.encode("ascii")).hexdigest()


def _canonical(value) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=True, sort_keys=True)


def _bounded(module, reply: str) -> None:
    assert len(reply) <= module.REPLY_CHAR_BUDGET, len(reply)
    assert reply.isascii()


# Test 1. Every reply is bounded, with no exception.

@pytest.mark.parametrize("detail", ("summary", "full"))
@pytest.mark.parametrize("limit", (1, 50, 500))
def test_paged_tool_catalogue_replies_are_bounded(
    repo_root, tmp_path, monkeypatch, detail, limit
):
    module, _calls = _paged(repo_root, tmp_path, monkeypatch, tools=_PAGED_TOOLS)
    replies = _walk(module.mcp.tools["list_toolbelt_tools"], limit=limit, detail=detail)
    assert len(replies) >= -(-362 // limit)
    for reply in replies:
        _bounded(module, reply)


@pytest.mark.parametrize("size", (0, 1, 176, 2000))
@pytest.mark.parametrize("limit", (1, 50, 500))
def test_paged_actor_replies_are_bounded(repo_root, tmp_path, monkeypatch, size, limit):
    module, _calls = _paged(repo_root, tmp_path, monkeypatch, actors=_PAGED_ACTORS[size])
    tool = module.mcp.tools["get_all_actors"]
    if size * (size // limit) > 200_000:
        # A complete walk of 2,000 actors one per page re-reads the listing
        # 2,000 times; its first, middle and last pages stand in for it.
        replies = [tool(offset=offset, limit=limit) for offset in (0, 1, 999, 1998, 1999, 2000)]
    else:
        replies = _walk(tool, limit=limit)
    for reply in replies:
        _bounded(module, reply)


def test_paged_actor_single_large_level_page_is_bounded(repo_root, tmp_path, monkeypatch):
    actors = [_paged_actor(i) for i in range(20_000)]
    module, _calls = _paged(repo_root, tmp_path, monkeypatch, actors=actors)
    reply = module.mcp.tools["get_all_actors"](limit=500)
    _bounded(module, reply)
    body = _page(reply)[1]
    assert body["count"] == 20_000 and body["budget_limited"] is True
    assert 0 < body["returned"] < 500


_ATTACK = "é中\U0001f600\"\\\n\t" * 3_000   # 30,000 code points; CJK, emoji, escapes


@pytest.mark.parametrize("case", (
    "category", "class_filter", "label_contains", "actor_path", "empty-tools",
    "empty-actors", "offset-equals-total", "oversized-summary", "oversized-full",
    "oversized-key", "escape-heavy",
))
def test_paged_attack_inputs_stay_bounded(repo_root, tmp_path, monkeypatch, case):
    actors = list(_PAGED_ACTORS[176])
    tools = list(_PAGED_TOOLS)
    if case == "empty-tools":
        tools = []
    elif case == "empty-actors":
        actors = []
    elif case in ("oversized-summary", "oversized-full"):
        tools.append(_paged_tool(900, name="tool_huge", description="d" * 30_000))
    elif case == "oversized-key":
        actors.append(_paged_actor(900, path="/P/" + "k" * 30_000, label="x" * 30_000))
    elif case == "escape-heavy":
        actors.append(_paged_actor(901, label=_ATTACK[:15_000]))
        tools.append(_paged_tool(901, name="tool_é中", description=_ATTACK[:9_000]))
    module, _calls = _paged(repo_root, tmp_path, monkeypatch, tools=tools, actors=actors)
    list_tools = module.mcp.tools["list_toolbelt_tools"]
    get_actors = module.mcp.tools["get_all_actors"]
    if case in ("category", "class_filter", "label_contains", "actor_path"):
        replies = [list_tools(category=_ATTACK)] if case == "category" else [
            get_actors(**{case: _ATTACK})]
    elif case == "offset-equals-total":
        replies = [list_tools(offset=362), get_actors(offset=176)]
    else:
        replies = (_walk(list_tools, detail="full" if case == "oversized-full" else "summary")
                   + _walk(get_actors))
    for reply in replies:
        _bounded(module, reply)


# Test 2. Complete enumeration.

@pytest.mark.parametrize(("listing", "limit"), (
    ("tools-summary", 50), ("tools-full", 7), ("actors-176", 50), ("actors-2000", 500),
    ("actors-2000", 7), ("actors-placeholders", 3),
))
def test_paged_walk_enumerates_every_key_exactly_once(
    repo_root, tmp_path, monkeypatch, listing, limit
):
    actors = list(_PAGED_ACTORS[2000 if listing == "actors-2000" else 176])
    if listing == "actors-placeholders":
        for i in (3, 4, 90):
            actors[i] = dict(actors[i], label="x" * 25_000)
    module, _calls = _paged(repo_root, tmp_path, monkeypatch, tools=_PAGED_TOOLS, actors=actors)
    if listing.startswith("tools"):
        replies = _walk(module.mcp.tools["list_toolbelt_tools"], limit=limit,
                        detail=listing.split("-")[1])
        source, key, items, count = _PAGED_TOOLS, "name", "tools", "total"
    else:
        replies = _walk(module.mcp.tools["get_all_actors"], limit=limit)
        source, key, items, count = actors, "path", "actors", "count"
    seen, expected_offset, omitted = [], 0, 0
    for index, reply in enumerate(replies):
        body = _page(reply)[1]
        assert body["offset"] == expected_offset
        assert body[count] == len(source)
        assert body["returned"] == len(body[items]) >= 1
        last = index == len(replies) - 1
        assert body["complete"] is last
        assert body["next_offset"] == (None if last else body["offset"] + body["returned"])
        assert body["omitted_count"] == sum(1 for e in body[items] if e.get("omitted"))
        omitted += body["omitted_count"]
        seen += [e[key] for e in body[items]]
        expected_offset += body["returned"]
    assert seen == sorted(e[key] for e in source)
    assert len(seen) == len(set(seen)) == len(source)
    assert omitted == (3 if listing == "actors-placeholders" else 0)


# Test 3. Order and unique keys.

def test_paged_pages_do_not_depend_on_bridge_order(repo_root, tmp_path, monkeypatch):
    ordered = sorted(_PAGED_ACTORS[176], key=lambda a: a["path"])
    walks = []
    for actors in (ordered, list(reversed(ordered)), _shuffled(ordered, 7)):
        module, _calls = _paged(repo_root, tmp_path, monkeypatch, actors=actors,
                                tools=list(reversed(_PAGED_TOOLS)) if walks else _PAGED_TOOLS)
        walks.append(_walk(module.mcp.tools["get_all_actors"], limit=30)
                     + _walk(module.mcp.tools["list_toolbelt_tools"], limit=30))
    assert walks[0] == walks[1] == walks[2]


_LONG_DUPLICATE = "/P/" + "d" * 50_000


@pytest.mark.parametrize("case", (
    "tools-identical", "tools-differing", "actors-identical", "actors-differing",
    "actors-outside-label-filter", "actors-outside-path-filter", "actors-long-key",
))
def test_paged_duplicate_keys_reject_the_whole_listing(repo_root, tmp_path, monkeypatch, case):
    tools, actors = list(_PAGED_TOOLS), list(_PAGED_ACTORS[176])
    kwargs: dict = {}
    if case == "tools-identical":
        tools.append(dict(tools[5]))
    elif case == "tools-differing":
        tools.append(dict(tools[5], description="another"))
    elif case == "actors-identical":
        actors.append(dict(actors[5]))
    elif case == "actors-differing":
        actors.append(dict(actors[5], label="another"))
    elif case.startswith("actors-outside"):
        actors.append(dict(actors[5], label="another"))
        # The filter selects a different actor, so the duplicate lies outside it.
        kwargs = ({"label_contains": actors[9]["label"]} if case.endswith("label-filter")
                  else {"actor_path": actors[9]["path"]})
    else:
        actors += [_paged_actor(1000, path=_LONG_DUPLICATE), _paged_actor(1001, path=_LONG_DUPLICATE)]
    module, calls = _paged(repo_root, tmp_path, monkeypatch, tools=tools, actors=actors)
    tool = module.mcp.tools["list_toolbelt_tools" if case.startswith("tools") else "get_all_actors"]
    with pytest.raises(ValueError, match="^malformed bridge reply: ") as error:
        tool(**kwargs)
    assert len(calls) == 1
    message = str(error.value)
    assert "share one" in message
    if case == "actors-long-key":
        assert len(message) < 300
        assert _expected_sha(json.dumps(_LONG_DUPLICATE, ensure_ascii=True)) in message
        assert "d" * 300 not in message


def test_paged_changing_duplicate_is_refused_on_the_first_call(repo_root, tmp_path, monkeypatch):
    """The r2 counterexample: a duplicate whose value changes between page calls."""
    base = [_paged_actor(i) for i in range(4)]

    def listing(command, params, call):
        labels = ("a", "b") if call == 1 else ("c", "b")
        dup = [_paged_actor(10, path="/P/dup", label=label) for label in labels]
        return {"actors": base + dup, "count": 6}

    module, calls = _paged(repo_root, tmp_path, monkeypatch, script=listing)
    tool = module.mcp.tools["get_all_actors"]
    with pytest.raises(ValueError, match="^malformed bridge reply: "):
        tool(limit=5)
    assert len(calls) == 1
    with pytest.raises(ValueError, match="^malformed bridge reply: "):
        tool(offset=5, limit=5)


def test_paged_unique_keys_enumerate_exactly_once_while_values_change(
    repo_root, tmp_path, monkeypatch
):
    """The unique-key twin: a value changes between page calls; keys arrive once."""
    def listing(command, params, call):
        actors = [_paged_actor(i) for i in range(6)]
        actors[5] = dict(actors[5], label="a" if call == 1 else "c")
        return {"actors": actors, "count": 6}

    module, _calls = _paged(repo_root, tmp_path, monkeypatch, script=listing)
    pages = [_page(reply)[1] for reply in _walk(module.mcp.tools["get_all_actors"], limit=5)]
    assert [a["path"] for p in pages for a in p["actors"]] == sorted(
        _paged_actor(i)["path"] for i in range(6))
    assert len({p["keys_digest"] for p in pages}) == 1
    assert len({p["listing_digest"] for p in pages}) == 2


# Test 4. Digests.

def test_paged_digests_follow_their_definitions(repo_root, tmp_path, monkeypatch):
    actors = list(_PAGED_ACTORS[176])
    module, _calls = _paged(repo_root, tmp_path, monkeypatch, tools=_PAGED_TOOLS, actors=actors)
    get_actors = module.mcp.tools["get_all_actors"]
    first, again = _page(get_actors())[1], _page(get_actors(offset=50))[1]
    ordered = sorted(actors, key=lambda a: a["path"])
    assert first["listing_digest"] == again["listing_digest"] == _expected_sha(_canonical(ordered))
    assert first["keys_digest"] == again["keys_digest"] == _expected_sha(
        _canonical([a["path"] for a in ordered]))
    assert first["listing_digest"] != first["keys_digest"]

    actors[0] = dict(actors[0], location={"x": -1.0, "y": 0.0, "z": 0.0})
    moved = _page(get_actors())[1]
    assert moved["keys_digest"] == first["keys_digest"]
    assert moved["listing_digest"] != first["listing_digest"]

    actors.append(_paged_actor(5000))
    added = _page(get_actors())[1]
    assert added["keys_digest"] != first["keys_digest"]
    assert added["listing_digest"] != moved["listing_digest"]

    list_tools = module.mcp.tools["list_toolbelt_tools"]
    summary, full = (_page(list_tools(detail=d))[1] for d in ("summary", "full"))
    module_tools = [dict(t) for t in _PAGED_TOOLS]
    module_tools[0]["icon"] = "changed"
    monkeypatch.setattr(module, "_send", lambda command, params=None, timeout=None: {
        "tools": module_tools, "count": 362})
    summary2, full2 = (_page(list_tools(detail=d))[1] for d in ("summary", "full"))
    assert summary2["listing_digest"] == summary["listing_digest"]
    assert full2["listing_digest"] != full["listing_digest"]
    assert full2["keys_digest"] == full["keys_digest"] == summary["keys_digest"]
    projected = [{k: t[k] for k in _SUMMARY_KEYS} for t in sorted(_PAGED_TOOLS,
                                                                  key=lambda t: t["name"])]
    assert summary["listing_digest"] == _expected_sha(_canonical(projected))


def test_paged_placeholder_hashes_follow_their_definitions(repo_root, tmp_path, monkeypatch):
    key = "/P/é\"\\\U0001f600" + "q" * 300
    big = _paged_actor(1, path=key, label="x" * 25_000)
    module, _calls = _paged(repo_root, tmp_path, monkeypatch, actors=[big])
    holder = _page(module.mcp.tools["get_all_actors"]())[1]["actors"][0]
    assert holder["key_omitted"] is True and holder["omitted"] is True
    literal = json.dumps(key, ensure_ascii=True)
    assert literal.startswith('"') and "\\u00e9" in literal and "\\ud83d\\ude00" in literal
    assert holder["key_sha256"] == _expected_sha(literal)
    assert holder["key_sha256"] != _expected_sha(literal[1:-1])   # control: quotes count
    assert holder["item_sha256"] == _expected_sha(_canonical(big))
    assert holder["omitted_chars"] == len(json.dumps(big, separators=(",", ":"), ensure_ascii=True))


# Test 5a. Direct-call validation, before any bridge request.

@pytest.mark.parametrize(("tool", "kwargs"), [
    (tool, kwargs)
    for tool in ("list_toolbelt_tools", "get_all_actors")
    for kwargs in ({"offset": -1}, {"limit": 0}, {"limit": 501}, {"offset": True},
                   {"limit": False}, {"offset": "0"}, {"limit": 1.5}, {"limit": 2.0},
                   {"offset": None})
] + [
    ("list_toolbelt_tools", {"detail": "tiny"}), ("list_toolbelt_tools", {"detail": None}),
    ("list_toolbelt_tools", {"category": 5}), ("get_all_actors", {"class_filter": None}),
    ("get_all_actors", {"label_contains": ["x"]}), ("get_all_actors", {"actor_path": 7}),
], ids=lambda value: value if isinstance(value, str) else repr(value))
def test_paged_invalid_arguments_are_rejected_before_any_bridge_request(
    repo_root, tmp_path, monkeypatch, tool, kwargs
):
    module, calls = _paged(repo_root, tmp_path, monkeypatch, tools=_PAGED_TOOLS,
                           actors=_PAGED_ACTORS[176])
    with pytest.raises(ValueError):
        module.mcp.tools[tool](**kwargs)
    assert calls == []


@pytest.mark.parametrize("tool", ("list_toolbelt_tools", "get_all_actors"))
def test_paged_offset_boundaries(repo_root, tmp_path, monkeypatch, tool):
    module, calls = _paged(repo_root, tmp_path, monkeypatch, tools=_PAGED_TOOLS,
                           actors=_PAGED_ACTORS[176])
    total = 362 if tool == "list_toolbelt_tools" else 176
    with pytest.raises(ValueError, match="restart from offset 0"):
        module.mcp.tools[tool](offset=total + 1)
    assert len(calls) == 1
    body = _page(module.mcp.tools[tool](offset=total))[1]
    assert (body["returned"], body["complete"], body["next_offset"]) == (0, True, None)


# Test 5b. Schema shape: the annotations and defaults an SDK derives its schema from.

def test_paged_tool_signatures_carry_integer_and_string_parameters(
    repo_root, tmp_path, monkeypatch
):
    module, _calls = _paged(repo_root, tmp_path, monkeypatch, tools=[], actors=[])
    expected = {
        "list_toolbelt_tools": [("category", str, ""), ("offset", int, 0), ("limit", int, 50),
                                ("detail", str, "summary")],
        "get_all_actors": [("class_filter", str, ""), ("offset", int, 0), ("limit", int, 50),
                           ("label_contains", str, ""), ("actor_path", str, "")],
    }
    for name, params in expected.items():
        signature = inspect.signature(module.mcp.tools[name], eval_str=True)
        assert [(p.name, p.annotation, p.default) for p in signature.parameters.values()] == params
        assert signature.return_annotation is str


# Test 6. Filtering.

def test_paged_filters_apply_before_paging_and_are_never_echoed(
    repo_root, tmp_path, monkeypatch
):
    actors = [_paged_actor(i) for i in range(40)]
    actors[3] = dict(actors[3], label="STRASSE crossing")
    actors[4] = dict(actors[4], label="straße crossing")
    actors[5] = dict(actors[5], label=None)
    actors[6] = dict(actors[6], label=5)
    module, calls = _paged(repo_root, tmp_path, monkeypatch, tools=_PAGED_TOOLS, actors=actors)
    get_actors = module.mcp.tools["get_all_actors"]
    category, class_filter = "Exact Category é #1", "Exact_Class_Filter_Value"
    module.mcp.tools["list_toolbelt_tools"](category=category)
    get_actors(class_filter=class_filter)
    assert calls == [("list_tools", {"category": category}),
                     ("get_all_actors", {"class_filter": class_filter})]

    body = _page(get_actors(label_contains="Straße"))[1]
    assert sorted(a["name"] for a in body["actors"]) == ["A_00003", "A_00004"]
    assert body["count"] == body["returned"] == 2
    labels = _page(get_actors(label_contains="label_000"))[1]
    assert {a["name"] for a in labels["actors"]} == {f"A_{i:05d}" for i in range(40)} - {
        "A_00003", "A_00004", "A_00005", "A_00006"}
    one = _page(get_actors(actor_path=actors[7]["path"]))[1]
    assert one["count"] == 1 and one["actors"] == [actors[7]]
    none = _page(get_actors(actor_path=actors[7]["path"][:-1]))[1]
    assert (none["count"], none["actors"], none["complete"]) == (0, [], True)
    both = _page(get_actors(actor_path=actors[7]["path"], label_contains="nomatch"))[1]
    assert both["count"] == 0
    both = _page(get_actors(actor_path=actors[7]["path"], label_contains="00007"))[1]
    assert both["count"] == 1

    needle, path = "Needle-Not-Echoed-é", "/Path/Not/Echoed/Anywhere"
    for reply in (get_actors(label_contains=needle), get_actors(actor_path=path),
                  get_actors(class_filter=class_filter),
                  module.mcp.tools["list_toolbelt_tools"](category=category)):
        for text in (needle, path, class_filter, category,
                     json.dumps(needle, ensure_ascii=True)[1:-1],
                     json.dumps(category, ensure_ascii=True)[1:-1]):
            assert text not in reply


# Test 7. Compatibility.

def test_paged_replies_keep_compatible_fields_and_entry_text(repo_root, tmp_path, monkeypatch):
    tools = list(_PAGED_TOOLS) + [_paged_tool(950, name="tool_é", description="café")]
    module, _calls = _paged(repo_root, tmp_path, monkeypatch, tools=tools,
                            actors=_PAGED_ACTORS[176])
    assert set(module.mcp.tools) - {"list_toolbelt_tools", "get_all_actors"} == _PAGED_OTHER_TOOLS
    assert {"list_toolbelt_tools", "get_all_actors"} <= set(module.mcp.tools)
    list_tools = module.mcp.tools["list_toolbelt_tools"]
    summaries = _walk(list_tools, limit=500)
    for summary in summaries:
        first, body = _page(summary)
        assert first == "// 363 tools registered"
        assert list(body) == ["total", "offset", "limit", "returned", "next_offset", "complete",
                              "budget_limited", "omitted_count", "listing_digest",
                              "keys_digest", "detail", "tools"]
        assert body["total"] == 363 and body["detail"] == "summary"
        for entry in body["tools"]:
            assert list(entry) == _SUMMARY_KEYS
    assert "tool_\\u00e9" in summaries[-1] and "caf\\u00e9" in summaries[-1]
    by_name = {t["name"]: t for t in tools}
    for reply in _walk(list_tools, limit=500, detail="full"):
        for entry in _page(reply)[1]["tools"]:
            source = by_name[entry["name"]]
            assert list(entry.items()) == list(source.items())
            assert json.dumps(source, separators=(",", ":"), ensure_ascii=True) in reply

    actors = _page(module.mcp.tools["get_all_actors"]())[1]
    assert list(actors) == ["count", "offset", "limit", "returned", "next_offset", "complete",
                            "budget_limited", "omitted_count", "listing_digest", "keys_digest",
                            "actors"]
    assert actors["count"] == 176

    instructions = module.mcp.instructions
    for phrase in ("list_toolbelt_tools — list registered tools, one bounded page per call",
                   "get_all_actors      — list level actors, one bounded page per call",
                   "Paged listings: list_toolbelt_tools and get_all_actors return one page "
                   "per call, at most 24,000 characters of ASCII JSON.",
                   "rejected as malformed",
                   "restart from offset 0, at most twice"):
        assert phrase in instructions, phrase
    for retired in ("see every tool available", "snapshot the level"):
        assert retired not in instructions


# Test 8. Placeholders.

def _sized_actor(i: int, chars: int) -> dict:
    """An actor whose serialized form is exactly `chars` characters."""
    entry = _paged_actor(i, label="")
    entry["label"] = "y" * (chars - len(json.dumps(entry, separators=(",", ":"))))
    assert len(json.dumps(entry, separators=(",", ":"), ensure_ascii=True)) == chars
    return entry


def test_paged_placeholders_replace_only_oversized_entries(repo_root, tmp_path, monkeypatch):
    module, _calls = _paged(repo_root, tmp_path, monkeypatch, actors=[])
    limit = module.ITEM_CHAR_LIMIT
    exact, over = _sized_actor(1, limit), _sized_actor(2, limit + 1)
    long_key = _paged_actor(3, path="/P/" + "k" * 400, label="z" * (limit + 10))
    actors = [exact, over, long_key, _paged_actor(4)]
    monkeypatch.setattr(module, "_send", lambda command, params=None, timeout=None: {
        "actors": actors, "count": 4})
    pages = [_page(r)[1] for r in _walk(module.mcp.tools["get_all_actors"], limit=1, step_bound=10)]
    entries = {p["actors"][0].get("path", "key-omitted"): p for p in pages}
    assert entries[exact["path"]]["actors"] == [exact]
    assert entries[exact["path"]]["omitted_count"] == 0
    assert entries[over["path"]]["actors"] == [{
        "path": over["path"], "omitted": True, "omitted_chars": limit + 1,
        "item_sha256": _expected_sha(_canonical(over))}]
    assert entries[over["path"]]["omitted_count"] == 1
    hidden = entries["key-omitted"]["actors"][0]
    assert list(hidden) == ["key_omitted", "key_sha256", "omitted", "omitted_chars", "item_sha256"]
    assert hidden["key_sha256"] == _expected_sha(json.dumps(long_key["path"], ensure_ascii=True))
    assert sum(p["returned"] for p in pages) == 4
    walk = _walk(module.mcp.tools["get_all_actors"], step_bound=4)
    assert sum(_page(r)[1]["omitted_count"] for r in walk) == 2


# Test 9. Malformed bridge replies.

@pytest.mark.parametrize("kind", (
    "not-an-object", "missing-field", "field-not-a-list", "entry-not-an-object",
    "missing-key", "null-key", "non-string-key", "duplicate-key",
))
@pytest.mark.parametrize("tool", ("list_toolbelt_tools", "get_all_actors"))
def test_paged_malformed_bridge_replies_fail_closed(repo_root, tmp_path, monkeypatch, kind, tool):
    field, key = ("tools", "name") if tool == "list_toolbelt_tools" else ("actors", "path")
    good = [_paged_tool(i) if field == "tools" else _paged_actor(i) for i in range(3)]
    result: object = {field: good}
    if kind == "not-an-object":
        result = [good]
    elif kind == "missing-field":
        result = {"count": 3}
    elif kind == "field-not-a-list":
        result = {field: {"0": good[0]}}
    elif kind == "entry-not-an-object":
        result = {field: good + ["not an entry"]}
    elif kind == "missing-key":
        result = {field: good + [{k: v for k, v in good[0].items() if k != key}]}
    elif kind == "null-key":
        result = {field: good + [dict(good[0], **{key: None})]}
    elif kind == "non-string-key":
        result = {field: good + [dict(good[0], **{key: 12})]}
    else:
        result = {field: good + [dict(good[0])]}
    module, calls = _paged(repo_root, tmp_path, monkeypatch,
                           script=lambda command, params, call: result)
    returned = []
    with pytest.raises(ValueError, match="^malformed bridge reply: "):
        returned.append(module.mcp.tools[tool]())
    assert returned == [] and len(calls) == 1


# Test 10. Protected metadata.

def test_paged_extra_fields_cannot_overwrite_paging_fields(repo_root, tmp_path, monkeypatch):
    module, _calls = _paged(repo_root, tmp_path, monkeypatch, actors=[])
    items = [_paged_actor(i) for i in range(3)]
    protected = ("count", "actors", "offset", "limit", "returned", "next_offset", "complete",
                 "budget_limited", "omitted_count", "listing_digest", "keys_digest")
    for name in protected:
        with pytest.raises(ValueError, match="would overwrite a paging field"):
            module._page_listing(items, key_field="path", items_field="actors",
                                 count_field="count", offset=0, limit=50,
                                 extra=((name, "x"),))
    with pytest.raises(ValueError, match="would overwrite a paging field"):
        module._page_listing(items, key_field="path", items_field="actors", count_field="count",
                             offset=0, limit=50, extra=(("detail", "a"), ("detail", "b")))
    body = json.loads(module._page_listing(items, key_field="path", items_field="actors",
                                           count_field="count", offset=0, limit=50,
                                           extra=(("detail", "full"),)))
    assert body["detail"] == "full" and body["returned"] == 3 and body["next_offset"] is None


def _exact_landing(module, target: int) -> tuple[list, dict]:
    """A 102-actor listing whose last page, offset 100 and limit 2, has a reply of
    exactly `target` characters when both of its actors are delivered.

    With three digits in the total and one in the entry count, the worst-case
    metadata bound equals that page's actual metadata, so the sizing decides
    at the exact character.
    """
    small = [_paged_actor(i) for i in range(100)]
    first = _paged_actor(200, path="/Z/Big_1", label="f" * 11_000)
    second = _paged_actor(201, path="/Z/Big_2", label="")
    digests = ("sha256:" + "0" * 64, "sha256:" + "1" * 64)
    skeleton = len(module._skeleton("", "count", "actors", 102, 100, 2, 2, None, False, 0,
                                    digests, ()))
    fixed = skeleton + len(json.dumps(first, separators=(",", ":"))) + 1
    second["label"] = "s" * (target - fixed - len(json.dumps(second, separators=(",", ":"))))
    return small + [first, second], {"offset": 100, "limit": 2}


def test_paged_exact_budget_reply_is_delivered_unflagged(repo_root, tmp_path, monkeypatch):
    module, _calls = _paged(repo_root, tmp_path, monkeypatch, actors=[])
    actors, kwargs = _exact_landing(module, module.REPLY_CHAR_BUDGET)
    monkeypatch.setattr(module, "_send", lambda command, params=None, timeout=None: {
        "actors": actors, "count": 102})
    reply = module.mcp.tools["get_all_actors"](**kwargs)
    body = _page(reply)[1]
    assert len(reply) == module.REPLY_CHAR_BUDGET
    assert (body["returned"], body["budget_limited"], body["omitted_count"]) == (2, False, 0)
    assert body["complete"] is True


# Test 11. Incremental sizing, by independent instrumentation.

class _CountingJson:
    """Stands in for mcp_server's `json`. It records each dumps() of an entry
    object by identity, telling canonical serializations (sort_keys) from reply
    ones. It never reads a helper counter."""

    def __init__(self, entry_ids: set):
        self.entry_ids, self.reply, self.canonical = entry_ids, [], []

    def dumps(self, obj, **kwargs):
        if id(obj) in self.entry_ids:
            (self.canonical if kwargs.get("sort_keys") else self.reply).append(id(obj))
        return json.dumps(obj, **kwargs)

    def __getattr__(self, name):
        return getattr(json, name)


def _counted_walk(module, monkeypatch, actors, limit):
    tool, rows, replies, offset = module.mcp.tools["get_all_actors"], [], [], 0
    ids = {id(a) for a in actors}
    while True:
        spy = _CountingJson(ids)
        with monkeypatch.context() as patch:
            patch.setattr(module, "json", spy)
            reply = tool(offset=offset, limit=limit)
        body = _page(reply)[1]
        replies.append(reply)
        rows.append((body["returned"], len(spy.reply), len(set(spy.reply)), sorted(spy.canonical)))
        if body["next_offset"] is None:
            return rows, replies
        offset = body["next_offset"]


def test_paged_sizing_serializes_each_entry_once(repo_root, tmp_path, monkeypatch):
    actors = _PAGED_ACTORS[2000]
    module, _calls = _paged(repo_root, tmp_path, monkeypatch, actors=actors)
    rows, replies = _counted_walk(module, monkeypatch, actors, 500)
    every = sorted(id(a) for a in actors)
    assert len(rows) > 1
    for returned, reply_dumps, distinct, canonical in rows:
        assert returned <= reply_dumps <= returned + 1
        assert distinct == reply_dumps
        assert canonical == every

    # Failing control: a reply serializer that bypasses the module's json binding
    # gives byte-identical pages, and only the lower bound notices it.
    monkeypatch.setattr(module, "_ser", lambda obj: json.dumps(
        obj, separators=(",", ":"), ensure_ascii=True))
    bypass_rows, bypass_replies = _counted_walk(module, monkeypatch, actors, 500)
    assert bypass_replies == replies
    assert all(reply_dumps == 0 for _r, reply_dumps, _d, _c in bypass_rows)
    assert not all(r <= dumps <= r + 1 for r, dumps, _d, _c in bypass_rows)


# Test 12. The worst-case bound, the configuration guard and the final check.

_PAGED_DIGESTS = ("sha256:" + "0" * 64, "sha256:" + "1" * 64)


def _bound_cases():
    cases = []
    for total in (0, 1, 9, 10, 11, 99, 100, 999, 1000, 1001, 9999, 10000, 123456):
        for limit in (1, 7, 50, 500):
            offsets = sorted({0, max(0, total - 1), max(0, total - limit), total // 2, total})
            for offset in offsets:
                want = min(limit, total - offset)
                for n in sorted({0, 1, 9, 10, 11, want - 1, want} & set(range(want + 1))):
                    for prefix, count, items, extra in (
                        ("", "count", "actors", ()),
                        (f"// {total} tools registered\n", "total", "tools",
                         (("detail", "summary"),)),
                        (f"// {'9' * 200} tools registered\n", "total", "tools",
                         (("detail", "full"),)),
                    ):
                        cases.append((prefix, count, items, total, offset, limit, n, extra))
    return cases


def test_paged_metadata_bound_covers_every_realizable_shape(repo_root, tmp_path, monkeypatch):
    module, _calls = _paged(repo_root, tmp_path, monkeypatch, actors=[])
    cases = _bound_cases()
    assert len(cases) == 2004
    tight = 0
    for prefix, count, items, total, offset, limit, n, extra in cases:
        bound = module._metadata_bound(prefix, count, items, total, offset, limit, n,
                                       _PAGED_DIGESTS, extra)
        nxt = offset + n if offset + n < total else None
        for by_budget in (False, True):
            for omitted in range(n + 1):
                actual = len(module._skeleton(prefix, count, items, total, offset, limit, n,
                                              nxt, by_budget, omitted, _PAGED_DIGESTS, extra))
                assert actual <= bound, (total, offset, limit, n, nxt, by_budget, omitted)
                tight += actual == bound
    assert tight > 0


def test_paged_configuration_guard_rejects_an_unfittable_item_limit(
    repo_root, tmp_path, monkeypatch
):
    module, calls = _paged(repo_root, tmp_path, monkeypatch, actors=_PAGED_ACTORS[176])
    assert _page(module.mcp.tools["get_all_actors"]())[1]["returned"] == 50
    monkeypatch.setattr(module, "ITEM_CHAR_LIMIT", module.REPLY_CHAR_BUDGET)
    with pytest.raises(ValueError, match="budget too small"):
        module.mcp.tools["get_all_actors"]()


def test_paged_final_check_fails_closed_when_sizing_under_reports(
    repo_root, tmp_path, monkeypatch
):
    module, _calls = _paged(repo_root, tmp_path, monkeypatch, actors=[])
    actors, kwargs = _exact_landing(module, module.REPLY_CHAR_BUDGET + 1)
    monkeypatch.setattr(module, "_send", lambda command, params=None, timeout=None: {
        "actors": actors, "count": 102})
    tool = module.mcp.tools["get_all_actors"]
    try:
        control = _page(tool(**kwargs))[1]
    except RuntimeError as error:
        raise AssertionError("the true bound admitted an over-budget page: " + str(error)) from None
    assert (control["returned"], control["budget_limited"]) == (1, True)
    true_bound = module._metadata_bound
    monkeypatch.setattr(module, "_metadata_bound", lambda *args: true_bound(*args) - 1)
    returned = []
    with pytest.raises(RuntimeError, match="exceeds its budget"):
        returned.append(tool(**kwargs))
    assert returned == []
