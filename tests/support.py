"""Dois processos reais em portas temporárias, com limpeza ao terminar."""

import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = "2026-07-28"


def unused_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class Servers:
    def __init__(self, root: Path = ROOT) -> None:
        self.root = root
        self.logs = tempfile.TemporaryDirectory(prefix="ponte-tests-")
        self.mcp_port = unused_port()
        self.agent_port = unused_port()
        self.mcp_url = f"http://127.0.0.1:{self.mcp_port}/mcp"
        self.agent_url = f"http://127.0.0.1:{self.agent_port}/a2a"
        self.env = {
            **os.environ,
            "REQUEST_STATE_SECRET": secrets.token_hex(32),
            "MCP_PORT": str(self.mcp_port),
            "A2A_PORT": str(self.agent_port),
            "MCP_URL": self.mcp_url,
            "A2A_URL": self.agent_url,
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        self.env.pop("PYTHONPATH", None)
        self.processes: dict[str, subprocess.Popen] = {}
        self.handles: dict[str, Any] = {}

    def start(self, name: str) -> None:
        path = "servidor-mcp/run.py" if name == "mcp" else "agente/run.py"
        handle = (Path(self.logs.name) / f"{name}.log").open("a")
        self.handles[name] = handle
        process = subprocess.Popen(
            [sys.executable, path],
            cwd=self.root,
            env=self.env,
            stdout=handle,
            stderr=handle,
        )
        self.processes[name] = process
        port = self.mcp_port if name == "mcp" else self.agent_port
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(self.log(name))
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    return
            except OSError:
                time.sleep(0.03)
        raise RuntimeError(f"Processo {name} não iniciou: {self.log(name)}")

    def stop(self, name: str) -> None:
        process = self.processes.pop(name, None)
        if process:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        handle = self.handles.pop(name, None)
        if handle:
            handle.close()

    def log(self, name: str) -> str:
        return (Path(self.logs.name) / f"{name}.log").read_text()

    def __enter__(self) -> "Servers":
        try:
            self.start("mcp")
            self.start("agent")
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *args: Any) -> None:
        for name in ("agent", "mcp"):
            self.stop(name)
        self.logs.cleanup()

    @staticmethod
    def post(
        url: str, body: dict[str, Any], headers: dict[str, str]
    ) -> tuple[int, dict[str, Any]]:
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", **headers},
        )
        try:
            response = urllib.request.urlopen(request, timeout=10)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            return response.status, json.loads(response.read())

    def mcp(
        self,
        method: str,
        params: dict[str, Any],
        *,
        trace: str | None = None,
        capabilities: dict[str, Any] | None = None,
        omit: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        meta = {
            "io.modelcontextprotocol/protocolVersion": PROTOCOL,
            "io.modelcontextprotocol/clientCapabilities": (
                {"elicitation": {"form": {}}} if capabilities is None else capabilities
            ),
        }
        if trace:
            meta["traceparent"] = trace
        if omit:
            meta.pop(omit)
        transport = {
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": PROTOCOL,
            "Mcp-Method": method,
        }
        if method == "tools/call":
            transport["Mcp-Name"] = params["name"]
        elif method == "resources/read":
            transport["Mcp-Name"] = params["uri"]
        transport.update(headers or {})
        return self.post(
            self.mcp_url,
            {
                "jsonrpc": "2.0",
                "id": secrets.token_hex(8),
                "method": method,
                "params": {**params, "_meta": meta},
            },
            transport,
        )

    def call(
        self, arguments: dict[str, Any], **extra: Any
    ) -> tuple[int, dict[str, Any]]:
        return self.mcp(
            "tools/call", {"name": "reservar_sala", "arguments": arguments, **extra}
        )

    def a2a(
        self, method: str, params: dict[str, Any], trace: str | None = None
    ) -> dict[str, Any]:
        return self.post(
            self.agent_url,
            {
                "jsonrpc": "2.0",
                "id": secrets.token_hex(8),
                "method": method,
                "params": params,
            },
            {"traceparent": trace} if trace else {},
        )[1]

    def send(
        self, text: str, task_id: str | None = None, trace: str | None = None
    ) -> dict[str, Any]:
        message = {
            "messageId": secrets.token_hex(8),
            "role": "ROLE_USER",
            "parts": [{"text": text}],
        }
        if task_id:
            message["taskId"] = task_id
        return self.a2a("SendMessage", {"message": message}, trace)


def arguments(
    room: str = "sala-garagem",
    start: str = "2026-11-03T14:00:00-03:00",
    end: str = "2026-11-03T15:00:00-03:00",
) -> dict[str, str]:
    return {"sala": room, "inicio": start, "fim": end, "responsavel": "Auditoria"}


def booking_text(value: dict[str, Any] | None = None) -> str:
    value = value or arguments()
    return "reservar " + " ".join(
        f"{key}={value[key]}" for key in ("sala", "inicio", "fim", "responsavel")
    )
