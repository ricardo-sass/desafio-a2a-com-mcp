"""Traduz rodadas MCP em estados A2A, mantendo requestState opaco por Task."""

import copy
import json
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from mcp.types import (
    CallToolResult,
    ElicitRequest,
    ElicitRequestFormParams,
    ElicitResult,
    InputRequiredResult,
)

from .mcp_client import MCP

Task = dict[str, Any]
TERMINAL_STATES = {"TASK_STATE_COMPLETED", "TASK_STATE_FAILED", "TASK_STATE_CANCELED"}


@dataclass(frozen=True)
class Pause:
    key: str
    alternatives: list[str]
    request_state: str


class Bridge:
    def __init__(self, mcp: MCP | None = None) -> None:
        self.mcp = mcp or MCP()
        self.tasks: dict[str, Task] = {}

    @staticmethod
    def parse(text: str) -> dict[str, str]:
        match = re.fullmatch(
            r"reservar sala=([^ ]+) inicio=(\S+) fim=(\S+) responsavel=(.+)", text
        )
        if not match:
            raise ValueError("pedido invalido")
        return dict(zip(("sala", "inicio", "fim", "responsavel"), match.groups()))

    @staticmethod
    def public(task: Task) -> Task:
        return copy.deepcopy(
            {key: value for key, value in task.items() if not key.startswith("_")}
        )

    def get(self, task_id: str) -> Task:
        if task_id not in self.tasks:
            raise ValueError("Task desconhecida")
        return self.public(self.tasks[task_id])

    @staticmethod
    def timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    def message(self, task: Task, state: str, text: str) -> None:
        message = {
            "messageId": "msg-" + secrets.token_hex(6),
            "role": "ROLE_AGENT",
            "parts": [{"text": text}],
            "taskId": task["id"],
            "contextId": task["contextId"],
        }
        task["status"] = {
            "state": state,
            "message": message,
            "timestamp": self.timestamp(),
        }
        task["history"].append(message)

    def apply_result(
        self, task: Task, result: CallToolResult | InputRequiredResult
    ) -> None:
        # A mesma tradução vale tanto para a primeira chamada quanto para retries.
        if isinstance(result, InputRequiredResult):
            requests = result.input_requests or {}
            if len(requests) != 1 or result.request_state is None:
                raise ValueError("Resposta MCP de pausa inválida")
            key, request = next(iter(requests.items()))
            if not isinstance(request, ElicitRequest) or not isinstance(
                request.params, ElicitRequestFormParams
            ):
                raise ValueError("O MCP solicitou um tipo de entrada não suportado")
            field = request.params.requested_schema["properties"]["sala"]
            alternatives = field.get("enum") or (
                [field["const"]] if "const" in field else []
            )
            if not alternatives:
                raise ValueError("Elicitation sem alternativas")
            task["_pause"] = Pause(key, list(alternatives), result.request_state)
            self.message(
                task,
                "TASK_STATE_INPUT_REQUIRED",
                "alternativas: " + ", ".join(alternatives),
            )
            return
        task["_pause"] = None
        if result.is_error:
            text = " ".join(
                part.text for part in result.content if hasattr(part, "text")
            )
            try:
                value = json.loads(text)
                text = value.get("erro", text) if isinstance(value, dict) else text
            except ValueError:
                pass
            self.message(task, "TASK_STATE_FAILED", text)
            return
        data = result.structured_content
        if not isinstance(data, dict):
            raise ValueError("Resposta MCP sem resultado estruturado")
        if data.get("reservado") is False:
            self.message(task, "TASK_STATE_CANCELED", "Reserva recusada")
            return
        required = {"reserva", "sala", "inicio", "fim", "responsavel"}
        if data.get("reservado") is not True or not required <= data.keys():
            raise ValueError("O MCP não confirmou uma reserva")
        task["artifacts"] = [
            {
                "artifactId": "art-" + secrets.token_hex(6),
                "name": "reserva",
                "parts": [
                    {
                        "text": json.dumps(
                            {**data, "politica": self.mcp.policy}, ensure_ascii=False
                        )
                    }
                ],
            }
        ]
        self.message(
            task,
            "TASK_STATE_COMPLETED",
            f"Reserva {data['reserva']} confirmada na {data['sala']}.",
        )

    async def send(self, params: dict[str, Any], trace: str | None = None) -> Task:
        message = params.get("message") or {}
        text = " ".join(
            part.get("text", "") for part in message.get("parts", []) if "text" in part
        )
        responses = None
        request_state = None
        if task_id := message.get("taskId"):
            task = self.tasks.get(task_id)
            if task is None:
                raise ValueError("Task desconhecida")
            current = task["status"]["state"]
            if current in TERMINAL_STATES:
                raise ValueError("Task terminal")
            if current != "TASK_STATE_INPUT_REQUIRED":
                raise ValueError("Task em execução")
            pause: Pause = task["_pause"]
            choice = (
                text.removeprefix("escolha=") if text.startswith("escolha=") else ""
            )
            task["history"].append(copy.deepcopy(message))
            if choice not in pause.alternatives and choice != "recusar":
                self.message(
                    task, current, "alternativas: " + ", ".join(pause.alternatives)
                )
                return self.public(task)
            response = (
                ElicitResult(action="decline")
                if choice == "recusar"
                else ElicitResult(action="accept", content={"sala": choice})
            )
            responses = {pause.key: response}
            request_state = pause.request_state
            # O trace da Task sobrevive a continuações sem header ou com outro trace.
            task["_trace"] = task["_trace"] or trace
        else:
            arguments = self.parse(text)
            task = {
                "id": "task-" + secrets.token_hex(6),
                "contextId": "ctx-" + secrets.token_hex(6),
                "status": {
                    "state": "TASK_STATE_SUBMITTED",
                    "timestamp": self.timestamp(),
                },
                "history": [copy.deepcopy(message)],
                "artifacts": [],
                "_arguments": arguments,
                "_trace": trace,
                "_pause": None,
            }
            self.tasks[task["id"]] = task
        task["status"] = {"state": "TASK_STATE_WORKING", "timestamp": self.timestamp()}
        try:
            result = await self.mcp.call(
                task["_arguments"],
                task["_trace"],
                input_responses=responses,
                request_state=request_state,
            )
            self.apply_result(task, result)
        except Exception as exc:
            # Uma falha de transporte/protocolo também termina a Task, sem deixá-la WORKING.
            task["_pause"] = None
            self.message(task, "TASK_STATE_FAILED", str(exc))
        return self.public(task)
