"""Adversarial contract tests for the custom same-user MCP control plane."""

from __future__ import annotations

import http.client
import importlib.util
import json
import queue
import socket
import sys
import threading
import time
import types
import urllib.error
import urllib.request

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
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"success":true,"result":{"status":"ok"}}'

    def success(request, timeout):
        captured["authorization"] = request.get_header("Authorization")
        return Response()

    monkeypatch.setattr(client.urllib.request, "urlopen", success)
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
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(client.urllib.request, "urlopen", unauthorized)
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
        client.urllib.request,
        "urlopen",
        lambda request, timeout: ReflectedFailure(),
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
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"success":true,"result":{"status":"ok"}}'

    def success(request, timeout):
        captured["authorization"] = request.get_header("Authorization")
        return Response()

    monkeypatch.setattr(client_module.urllib.request, "urlopen", success)
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
        client_module.urllib.request,
        "urlopen",
        lambda request, timeout: ReflectedFailure(),
    )
    with pytest.raises(client_module.ToolbeltError) as reflected:
        client._send(token)
    assert token not in str(reflected.value)
    assert "[REDACTED]" in str(reflected.value)

    def unauthorized(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(client_module.urllib.request, "urlopen", unauthorized)
    with pytest.raises(client_module.AuthenticationError) as exc_info:
        client.ping()
    assert token not in str(exc_info.value)
    assert token not in repr(exc_info.value)
