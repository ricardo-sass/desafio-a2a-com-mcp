import asyncio
import json
import os
import secrets
import unittest
from unittest.mock import AsyncMock, patch

from tests.support import arguments, booking_text

from mcp.types import (
    CallToolResult,
    ElicitRequest,
    ElicitRequestFormParams,
    InputRequiredResult,
    TextContent,
)
from agente.bridge import Bridge
from agente.mcp_client import MCP
from salas_mcp.domain import validate_arguments
from salas_mcp.errors import RequestStateError
from salas_mcp.state import seal, secret_key, unseal


class ComponentsTest(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(
            os.environ, {"REQUEST_STATE_SECRET": secrets.token_hex(32)}
        )
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_request_state_integrity_and_expiry(self):
        value = arguments()
        with patch("salas_mcp.state.time.time", return_value=1000):
            token = seal(value, "choice", ["sala-fusca"])
        with patch("salas_mcp.state.time.time", return_value=1001):
            self.assertEqual(unseal(token)["arguments"], value)
            for index in (0, 8, len(token) - 1):
                with self.subTest(index=index):
                    changed = (
                        token[:index]
                        + ("x" if token[index] != "x" else "y")
                        + token[index + 1 :]
                    )
                    with self.assertRaises(RequestStateError):
                        unseal(changed)
        with patch("salas_mcp.state.time.time", return_value=1900):
            with self.assertRaises(RequestStateError):
                unseal(token)

    def test_secret_required_and_minimum_size(self):
        for secret in ("", "11" * 31, "invalid"):
            with (
                self.subTest(secret=secret),
                patch.dict(os.environ, {"REQUEST_STATE_SECRET": secret}),
            ):
                with self.assertRaises(SystemExit):
                    secret_key()

    def test_fixed_parser(self):
        self.assertEqual(Bridge.parse(booking_text()), arguments())
        with self.assertRaises(ValueError):
            Bridge.parse("pedido livre")

    def test_sao_paulo_window(self):
        cases = [
            ("2026-11-04T08:00:00+00:00", "2026-11-04T09:00:00+00:00", False),
            ("2026-11-04T22:00:00+00:00", "2026-11-04T23:00:00+00:00", True),
            ("2026-11-04T23:00:00-03:00", "2026-11-05T01:00:00-03:00", False),
            ("2026-11-04T19:00:00-03:00", "2026-11-04T20:00:00.000001-03:00", False),
            ("2026-11-04T09:00:00", "2026-11-04T10:00:00", False),
            ("2026-11-04T08:00:00-03:00", "2026-11-04T10:00:00-03:00", True),
        ]
        for start, end, valid in cases:
            with self.subTest(start=start, end=end):
                error = validate_arguments(arguments("sala-aquario", start, end))
                self.assertEqual(error is None, valid)


def paused(token="opaque-state", rooms=None):
    return InputRequiredResult(
        input_requests={
            "choice": ElicitRequest(
                params=ElicitRequestFormParams(
                    message="Escolha",
                    requested_schema={
                        "type": "object",
                        "properties": {
                            "sala": {
                                "type": "string",
                                "enum": rooms or ["sala-fusca", "sala-mirante"],
                            }
                        },
                        "required": ["sala"],
                    },
                )
            )
        },
        request_state=token,
    )


class BridgeTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.mcp = MCP()
        self.mcp.policy = "2026-11-01"
        self.mcp.call = AsyncMock()
        self.bridge = Bridge(self.mcp)

    @staticmethod
    def message(text, task=None):
        value = {"parts": [{"text": text}], "messageId": "test", "role": "ROLE_USER"}
        if task:
            value["taskId"] = task
        return {"message": value}

    async def test_repeated_pause_and_trace_survive_retry(self):
        self.mcp.call.side_effect = [paused(), paused("second-state", ["sala-mirante"])]
        trace = "00-" + secrets.token_hex(16) + "-" + secrets.token_hex(8) + "-01"
        first = await self.bridge.send(self.message(booking_text()), trace)
        second = await self.bridge.send(self.message("escolha=sala-fusca", first["id"]))
        self.assertEqual(second["status"]["state"], "TASK_STATE_INPUT_REQUIRED")
        self.assertEqual(
            second["status"]["message"]["parts"][0]["text"],
            "alternativas: sala-mirante",
        )
        self.assertEqual(second["artifacts"], [])
        self.assertEqual(self.mcp.call.call_args.args[1], trace)
        self.assertEqual(
            self.mcp.call.call_args.kwargs["request_state"], "opaque-state"
        )
        self.assertNotIn("second-state", json.dumps(second))
        self.assertNotIn("request_state", json.dumps(second))

    async def test_working_task_can_be_observed(self):
        entered = asyncio.Event()
        release = asyncio.Event()

        async def delayed(*args, **kwargs):
            entered.set()
            await release.wait()
            return paused()

        self.mcp.call.side_effect = delayed
        running = asyncio.create_task(self.bridge.send(self.message(booking_text())))
        await entered.wait()
        task_id = next(iter(self.bridge.tasks))
        snapshot = self.bridge.get(task_id)
        self.assertEqual(snapshot["status"]["state"], "TASK_STATE_WORKING")
        snapshot["status"]["state"] = "changed"
        self.assertEqual(
            self.bridge.get(task_id)["status"]["state"], "TASK_STATE_WORKING"
        )
        release.set()
        await running

    async def test_invalid_choice_does_not_call_mcp_and_terminal_is_immutable(self):
        self.mcp.call.side_effect = [
            paused(),
            CallToolResult(
                content=[TextContent(type="text", text="recusado")],
                structured_content={"reservado": False, "motivo": "recusado"},
            ),
        ]
        first = await self.bridge.send(self.message(booking_text()))
        invalid = await self.bridge.send(
            self.message("escolha=inexistente", first["id"])
        )
        self.assertEqual(invalid["status"]["state"], "TASK_STATE_INPUT_REQUIRED")
        self.assertEqual(self.mcp.call.await_count, 1)
        canceled = await self.bridge.send(self.message("escolha=recusar", first["id"]))
        self.assertEqual(canceled["status"]["state"], "TASK_STATE_CANCELED")
        with self.assertRaises(ValueError):
            await self.bridge.send(self.message("escolha=sala-fusca", first["id"]))
        self.assertEqual(self.bridge.get(first["id"]), canceled)

    async def test_transport_failure_does_not_leave_task_working(self):
        self.mcp.call.side_effect = RuntimeError("MCP indisponível")
        task = await self.bridge.send(self.message(booking_text()))
        self.assertEqual(task["status"]["state"], "TASK_STATE_FAILED")
        self.assertEqual(
            task["status"]["message"]["parts"][0]["text"], "MCP indisponível"
        )


if __name__ == "__main__":
    unittest.main()
