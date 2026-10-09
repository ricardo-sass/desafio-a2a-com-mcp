"""Regressões por HTTP real, sem reutilizar dados alterados entre testes."""

import concurrent.futures
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

import jsonschema

from tests.support import Servers, arguments, booking_text

from salas_mcp.state import seal


class IntegrationTest(unittest.TestCase):
    def setUp(self):
        self.servers = Servers()
        self.servers.__enter__()
        self.addCleanup(self.servers.__exit__)

    def pause(self):
        value = arguments()
        status, response = self.servers.call(value)
        self.assertEqual(status, 200)
        result = response["result"]
        self.assertEqual(result["resultType"], "input_required")
        return value, next(iter(result["inputRequests"])), result["requestState"]

    def retry(self, value, key, token, action="accept", room="sala-fusca"):
        return self.servers.call(
            value,
            requestState=token,
            inputResponses={key: {"action": action, "content": {"sala": room}}},
        )

    def test_starter_validator(self):
        result = subprocess.run(
            [
                sys.executable,
                "validador/validar.py",
                "--agente",
                self.servers.agent_url.removesuffix("/a2a"),
                "--mcp",
                self.servers.mcp_url.removesuffix("/mcp"),
            ],
            cwd=self.servers.root,
            capture_output=True,
            text=True,
            timeout=90,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("36 passaram, 0 falharam", result.stdout)
        trace_id = result.stdout.splitlines()[0].split()[-1]
        self.assertIn(trace_id, self.servers.log("mcp"))

    def test_discovery_and_output_schema(self):
        _, response = self.servers.mcp("server/discover", {})
        self.assertIn("tools", response["result"]["capabilities"])
        self.assertIn("resources", response["result"]["capabilities"])
        _, response = self.servers.mcp("tools/list", {})
        tools = {tool["name"]: tool for tool in response["result"]["tools"]}
        self.assertEqual(
            set(tools), {"listar_salas", "consultar_disponibilidade", "reservar_sala"}
        )
        self.assertEqual(
            set(tools["reservar_sala"]["inputSchema"]["required"]),
            {"sala", "inicio", "fim", "responsavel"},
        )
        _, response = self.servers.mcp(
            "tools/call", {"name": "listar_salas", "arguments": {}}
        )
        data = response["result"]["structuredContent"]
        jsonschema.validate(data, tools["listar_salas"]["outputSchema"])
        self.assertEqual(json.loads(response["result"]["content"][0]["text"]), data)

    def test_stateless_metadata_headers_and_capability(self):
        params = {"name": "listar_salas", "arguments": {}}
        for missing in ("protocolVersion", "clientCapabilities"):
            with self.subTest(missing=missing):
                status, response = self.servers.mcp(
                    "tools/call", params, omit="io.modelcontextprotocol/" + missing
                )
                self.assertEqual(status, 400)
                self.assertEqual(response["error"]["code"], -32602)
        for header in ("MCP-Protocol-Version", "Mcp-Method", "Mcp-Name"):
            with self.subTest(header=header):
                _, response = self.servers.mcp(
                    "tools/call", params, headers={header: "divergente"}
                )
                self.assertEqual(response["error"]["code"], -32020)
        status, response = self.servers.mcp(
            "tools/call",
            {"name": "reservar_sala", "arguments": arguments()},
            capabilities={},
        )
        self.assertEqual(status, 400)
        self.assertEqual(response["error"]["code"], -32021)
        self.assertIn("requiredCapabilities", response["error"]["data"])

    def test_form_capability_is_required_per_request(self):
        params = {"name": "reservar_sala", "arguments": arguments()}
        # Uma declaração válida anterior não autoriza as chamadas seguintes.
        status, response = self.servers.mcp(
            "tools/call", params, capabilities={"elicitation": {"form": {}}}
        )
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["resultType"], "input_required")
        for capabilities in (
            {},
            {"elicitation": {}},
            {"elicitation": {"url": {}}},
            {"elicitation": {"form": None, "url": {}}},
        ):
            with self.subTest(capabilities=capabilities):
                status, response = self.servers.mcp(
                    "tools/call", params, capabilities=capabilities
                )
                self.assertEqual(status, 400)
                self.assertEqual(response["error"]["code"], -32021)
                self.assertEqual(
                    response["error"]["data"]["requiredCapabilities"],
                    {"elicitation": {"form": {}}},
                )
        status, response = self.servers.mcp(
            "tools/call",
            params,
            capabilities={"elicitation": {"form": {}, "url": {}}},
        )
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["resultType"], "input_required")

    def test_a2a_malformed_params_return_jsonrpc_errors(self):
        valid_message = {
            "messageId": "test",
            "role": "ROLE_USER",
            "parts": [{"text": booking_text()}],
        }
        cases = (
            [("SendMessage", params) for params in (None, [], [1], "invalid", 1, False)]
            + [
                ("SendMessage", {"message": message})
                for message in (None, [], "invalid", 1, {"parts": None}, {"parts": []})
            ]
            + [
                ("SendMessage", {"message": {**valid_message, "parts": parts}})
                for parts in ("invalid", ["text"], [None], [{"text": 1}], [{}])
            ]
            + [
                ("SendMessage", {"message": {**valid_message, "taskId": task_id}})
                for task_id in ([], {}, 1)
            ]
            + [("GetTask", {"id": task_id}) for task_id in (None, [], {}, 1)]
        )
        for index, (method, params) in enumerate(cases):
            with self.subTest(method=method, params=params):
                status, response = self.servers.post(
                    self.servers.agent_url,
                    {"jsonrpc": "2.0", "id": index, "method": method, "params": params},
                    {},
                )
                self.assertEqual(status, 200)
                self.assertEqual(response["jsonrpc"], "2.0")
                self.assertEqual(response["id"], index)
                self.assertEqual(response["error"]["code"], -32602)
                self.assertNotIn("result", response)
        # Requests inválidos não derrubam o processo nem impedem novas reservas.
        task = self.servers.send(booking_text())["result"]["task"]
        self.assertEqual(task["status"]["state"], "TASK_STATE_INPUT_REQUIRED")

    def test_request_state_restart_expiry_and_integrity(self):
        value, key, token = self.pause()
        for index in (0, 8, len(token) - 1):
            with self.subTest(index=index):
                changed = (
                    token[:index]
                    + ("x" if token[index] != "x" else "y")
                    + token[index + 1 :]
                )
                _, response = self.retry(value, key, changed)
                self.assertEqual(response["error"]["code"], -32602)
        _, response = self.retry({**value, "responsavel": "Adulterado"}, key, token)
        self.assertEqual(response["error"]["code"], -32602)
        with (
            patch.dict(
                os.environ,
                {"REQUEST_STATE_SECRET": self.servers.env["REQUEST_STATE_SECRET"]},
            ),
            patch("salas_mcp.state.time.time", return_value=time.time() - 901),
        ):
            expired = seal(value, key, ["sala-fusca"])
        _, response = self.retry(value, key, expired)
        self.assertEqual(response["error"]["code"], -32602)
        self.servers.stop("mcp")
        self.servers.start("mcp")
        _, response = self.retry(value, key, token)
        self.assertEqual(response["result"]["structuredContent"]["sala"], "sala-fusca")
        _, response = self.servers.mcp(
            "tools/call",
            {
                "name": "consultar_disponibilidade",
                "arguments": {
                    key: val
                    for key, val in {**value, "sala": "sala-fusca"}.items()
                    if key != "responsavel"
                },
            },
        )
        self.assertFalse(response["result"]["structuredContent"]["livre"])

    def test_decline_and_cancel_do_not_reserve(self):
        for action in ("decline", "cancel"):
            with self.subTest(action=action):
                value, key, token = self.pause()
                status, response = self.retry(value, key, token, action=action)
                self.assertEqual(status, 200)
                self.assertEqual(response["result"]["resultType"], "complete")
                self.assertFalse(response["result"].get("isError"))
                self.assertFalse(response["result"]["structuredContent"]["reservado"])
        status, response = self.servers.call(arguments("sala-fusca"))
        self.assertEqual(status, 200)
        self.assertTrue(response["result"]["structuredContent"]["reservado"])

    def test_sao_paulo_window_over_http(self):
        bad = arguments(
            "sala-aquario", "2026-11-04T23:00:00-03:00", "2026-11-05T01:00:00-03:00"
        )
        _, response = self.servers.call(bad)
        self.assertTrue(response["result"]["isError"])
        bad = arguments(
            "sala-aquario", "2026-11-04T08:00:00+00:00", "2026-11-04T09:00:00+00:00"
        )
        _, response = self.servers.call(bad)
        self.assertTrue(response["result"]["isError"])
        valid = arguments(
            "sala-aquario", "2026-11-04T22:00:00+00:00", "2026-11-04T23:00:00+00:00"
        )
        _, response = self.servers.call(valid)
        self.assertTrue(response["result"]["structuredContent"]["reservado"])

    def test_repeated_pause_task_isolation_and_trace(self):
        trace = "00-" + secrets.token_hex(16) + "-" + secrets.token_hex(8) + "-01"
        first = self.servers.send(booking_text(), trace=trace)["result"]["task"]
        second_args = {**arguments(), "responsavel": "Segundo"}
        second = self.servers.send(booking_text(second_args), trace=trace)["result"][
            "task"
        ]
        first_done = self.servers.send("escolha=sala-fusca", first["id"])["result"][
            "task"
        ]
        self.assertEqual(first_done["status"]["state"], "TASK_STATE_COMPLETED")
        again = self.servers.send("escolha=sala-fusca", second["id"])["result"]["task"]
        self.assertEqual(again["status"]["state"], "TASK_STATE_INPUT_REQUIRED")
        self.assertEqual(
            again["status"]["message"]["parts"][0]["text"], "alternativas: sala-mirante"
        )
        self.assertEqual(again["artifacts"], [])
        done = self.servers.send("escolha=sala-mirante", second["id"])["result"]["task"]
        self.assertEqual(done["status"]["state"], "TASK_STATE_COMPLETED")
        artifact = json.loads(done["artifacts"][0]["parts"][0]["text"])
        self.assertEqual(artifact["responsavel"], "Segundo")
        self.assertEqual(artifact["sala"], "sala-mirante")
        self.assertNotIn("requestState", json.dumps([first, second, again, done]))
        log = self.servers.log("mcp")
        lines = [
            line
            for line in log.splitlines()
            if line.startswith("method=") and "server/discover" not in line
        ]
        self.assertTrue(all(trace[3:35] in line for line in lines), log)
        methods = [re.search(r"method=(\S+)", line).group(1) for line in lines]
        self.assertLess(methods.index("tools/list"), methods.index("tools/call"))
        ids = [re.search(r" id=(\S+)", line).group(1) for line in lines]
        self.assertEqual(len(ids), len(set(ids)))

    @unittest.skipUnless(hasattr(signal, "SIGSTOP"), "Requer sinais POSIX")
    def test_get_task_while_mcp_is_blocked(self):
        paused = self.servers.send(booking_text())["result"]["task"]
        process = self.servers.processes["mcp"]
        with concurrent.futures.ThreadPoolExecutor() as pool:
            process.send_signal(signal.SIGSTOP)
            resumed = pool.submit(self.servers.send, "escolha=sala-fusca", paused["id"])
            try:
                deadline = time.monotonic() + 3
                current = None
                while time.monotonic() < deadline:
                    current = self.servers.a2a("GetTask", {"id": paused["id"]})[
                        "result"
                    ]["task"]
                    if current["status"]["state"] == "TASK_STATE_WORKING":
                        break
                    time.sleep(0.02)
                self.assertEqual(current["status"]["state"], "TASK_STATE_WORKING")
                self.assertFalse(resumed.done())
            finally:
                process.send_signal(signal.SIGCONT)
            done = resumed.result(timeout=10)["result"]["task"]
            self.assertEqual(done["status"]["state"], "TASK_STATE_COMPLETED")


if __name__ == "__main__":
    unittest.main()
