"""Binding A2A v1.0 assíncrono; GetTask pode observar chamadas em andamento."""

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

import jsonschema
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .bridge import Bridge


PARAM_SCHEMAS = {
    "SendMessage": {
        "type": "object",
        "required": ["message"],
        "properties": {
            "message": {
                "type": "object",
                "required": ["parts"],
                "properties": {
                    "taskId": {"type": "string", "minLength": 1},
                    "parts": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "required": ["text"],
                            "properties": {"text": {"type": "string"}},
                        },
                    },
                },
            }
        },
    },
    "GetTask": {
        "type": "object",
        "required": ["id"],
        "properties": {"id": {"type": "string", "minLength": 1}},
    },
}


def create_app() -> Starlette:
    bridge = Bridge()
    port = int(os.environ.get("A2A_PORT", "7300"))
    public_url = os.environ.get("A2A_URL", f"http://127.0.0.1:{port}/a2a")
    card = {
        "name": "Central de Salas",
        "description": "Reserva salas de reunião da Hill Valley Tech.",
        "provider": {
            "organization": "Hill Valley Tech",
            "url": "https://hillvalley.example",
        },
        "version": "1.0.0",
        "supportedInterfaces": [
            {"url": public_url, "protocolBinding": "JSONRPC", "protocolVersion": "1.0"}
        ],
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
            "extendedAgentCard": False,
        },
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": ["text/plain"],
        "skills": [
            {
                "id": "reservar-sala",
                "name": "Reservar sala",
                "description": "Reserva uma sala em um intervalo e oferece alternativas em caso de conflito.",
                "tags": ["salas", "agenda"],
                "inputModes": ["text/plain"],
                "outputModes": ["text/plain"],
            }
        ],
    }

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        async with bridge.mcp.connect():
            yield

    async def agent_card(request: Request) -> JSONResponse:
        return JSONResponse(card)

    async def rpc(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except ValueError:
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "JSON inválido"},
                }
            )
        if (
            not isinstance(body, dict)
            or body.get("jsonrpc") != "2.0"
            or "id" not in body
        ):
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32600, "message": "Request inválido"},
                }
            )
        request_id = body["id"]
        try:
            params = body.get("params", {})
            if not isinstance(params, dict):
                raise ValueError("params deve ser um objeto")
            if body.get("method") in PARAM_SCHEMAS:
                jsonschema.validate(params, PARAM_SCHEMAS[body["method"]])
            if body.get("method") == "GetTask":
                task = bridge.get(params["id"])
            elif body.get("method") == "SendMessage":
                task = await bridge.send(params, request.headers.get("traceparent"))
            else:
                return JSONResponse(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {"code": -32601, "message": "Método desconhecido"},
                    }
                )
            return JSONResponse(
                {"jsonrpc": "2.0", "id": request_id, "result": {"task": task}}
            )
        except (ValueError, KeyError, TypeError, jsonschema.ValidationError) as exc:
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32602,
                        "message": (
                            exc.message
                            if isinstance(exc, jsonschema.ValidationError)
                            else str(exc)
                        ),
                    },
                }
            )

    app = Starlette(
        routes=[
            Route("/.well-known/agent-card.json", agent_card),
            Route("/a2a", rpc, methods=["POST"]),
        ],
        lifespan=lifespan,
    )
    app.state.bridge = bridge
    return app


def main() -> None:
    uvicorn.run(
        create_app(),
        host="127.0.0.1",
        port=int(os.environ.get("A2A_PORT", "7300")),
        access_log=False,
    )
