"""Handlers de domínio sobre o transporte Streamable HTTP do SDK oficial MCP."""

import json
import logging
import os
from typing import Any

import jsonschema
import uvicorn
from mcp import MCPError
from mcp.server import Server, ServerRequestContext
from mcp.types import (
    INVALID_PARAMS,
    CallToolRequestParams,
    CallToolResult,
    ElicitRequest,
    ElicitRequestFormParams,
    ElicitResult,
    ErrorData,
    InputRequiredResult,
    JSONRPCError,
    ListResourcesResult,
    ListToolsResult,
    PaginatedRequestParams,
    ReadResourceRequestParams,
    ReadResourceResult,
    Resource,
    TextContent,
    TextResourceContents,
    Tool,
)
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .constants import ERROR_NO_ALTERNATIVES, MCP_PORT
from .domain import (
    POLICY,
    POLICY_VERSION,
    SALAS,
    alternatives,
    conflicts,
    create_reservation,
    validate_arguments,
)
from .errors import RequestStateError
from .state import seal, secret_key, unseal

logger = logging.getLogger("salas_mcp.requests")


def input_schema(*fields: str) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {field: {"type": "string", "minLength": 1} for field in fields},
        "required": list(fields),
        "additionalProperties": False,
    }


TOOLS = [
    Tool(
        name="listar_salas",
        description="Lista as salas de reunião e seus recursos.",
        input_schema=input_schema(),
        output_schema={
            "type": "object",
            "properties": {
                "salas": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "nome": {"type": "string"},
                            "capacidade": {"type": "integer"},
                            "recursos": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["id", "nome", "capacidade", "recursos"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["salas"],
            "additionalProperties": False,
        },
    ),
    Tool(
        name="consultar_disponibilidade",
        description="Consulta disponibilidade e conflitos em um intervalo.",
        input_schema=input_schema("sala", "inicio", "fim"),
    ),
    Tool(
        name="reservar_sala",
        description="Reserva uma sala ou oferece alternativas quando há conflito.",
        input_schema=input_schema("sala", "inicio", "fim", "responsavel"),
    ),
]
TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}


def text_result(value: dict[str, Any], *, error: bool = False) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(value, ensure_ascii=False))],
        structured_content=value,
        is_error=error,
    )


async def list_tools(
    ctx: ServerRequestContext, params: PaginatedRequestParams | None
) -> ListToolsResult:
    return ListToolsResult(tools=TOOLS)


async def list_resources(
    ctx: ServerRequestContext, params: PaginatedRequestParams | None
) -> ListResourcesResult:
    return ListResourcesResult(
        resources=[
            Resource(
                uri="politica://uso", name="Política de uso", mime_type="text/markdown"
            )
        ]
    )


async def read_resource(
    ctx: ServerRequestContext, params: ReadResourceRequestParams
) -> ReadResourceResult:
    if str(params.uri) != "politica://uso":
        raise MCPError(INVALID_PARAMS, "URI desconhecida", {"uri": str(params.uri)})
    return ReadResourceResult(
        contents=[
            TextResourceContents(uri=params.uri, mime_type="text/markdown", text=POLICY)
        ]
    )


def require_input(
    ctx: ServerRequestContext, arguments: dict[str, Any]
) -> CallToolResult | InputRequiredResult:
    rooms = alternatives(arguments)
    if not rooms:
        return text_result({"erro": ERROR_NO_ALTERNATIVES}, error=True)
    # No SDK 2.3.0, check_client_capability verifica apenas elicitation,
    # sem conferir o modo. A sessão stateless contém as capabilities deste request.
    capabilities = ctx.session.client_capabilities
    if (
        capabilities is None
        or capabilities.elicitation is None
        or capabilities.elicitation.form is None
    ):
        raise MCPError(
            -32021,
            "Client did not declare the form elicitation capability",
            {"requiredCapabilities": {"elicitation": {"form": {}}}},
        )
    key = "escolha_de_sala"
    return InputRequiredResult(
        input_requests={
            key: ElicitRequest(
                params=ElicitRequestFormParams(
                    mode="form",
                    message="A sala pedida esta ocupada nesse intervalo. Escolha uma alternativa.",
                    requested_schema={
                        "type": "object",
                        "properties": {"sala": {"type": "string", "enum": rooms}},
                        "required": ["sala"],
                    },
                )
            )
        },
        request_state=seal(arguments, key, rooms),
    )


async def call_tool(
    ctx: ServerRequestContext, params: CallToolRequestParams
) -> CallToolResult | InputRequiredResult:
    tool = TOOLS_BY_NAME.get(params.name)
    if tool is None:
        raise MCPError(INVALID_PARAMS, f"Tool desconhecida: {params.name}")
    arguments = params.arguments or {}
    try:
        jsonschema.validate(arguments, tool.input_schema)
    except jsonschema.ValidationError as exc:
        raise MCPError(INVALID_PARAMS, exc.message) from exc

    original = dict(arguments)
    if params.request_state is not None:
        try:
            saved = unseal(params.request_state)
        except RequestStateError as exc:
            raise MCPError(INVALID_PARAMS, str(exc)) from exc
        if params.name != "reservar_sala" or arguments != saved["arguments"]:
            raise MCPError(INVALID_PARAMS, "argumentos divergentes do requestState")
        responses = params.input_responses or {}
        if set(responses) != {saved["key"]}:
            raise MCPError(
                INVALID_PARAMS, "inputResponses incompatível com requestState"
            )
        answer = responses[saved["key"]]
        if not isinstance(answer, ElicitResult):
            raise MCPError(INVALID_PARAMS, "resposta de elicitation inválida")
        if answer.action in ("decline", "cancel"):
            return text_result({"reservado": False, "motivo": "recusado"})
        chosen = (answer.content or {}).get("sala")
        if chosen not in saved["alternatives"]:
            raise MCPError(INVALID_PARAMS, "escolha nao oferecida")
        original = dict(saved["arguments"])
        arguments = {**original, "sala": chosen}
    elif params.input_responses:
        raise MCPError(INVALID_PARAMS, "inputResponses exige requestState")

    if params.name == "listar_salas":
        return text_result({"salas": SALAS})
    if error := validate_arguments(arguments):
        return text_result({"erro": error}, error=True)
    occupied = conflicts(arguments)
    if params.name == "consultar_disponibilidade":
        return text_result(
            {
                "sala": arguments["sala"],
                "livre": not occupied,
                "conflitos": [
                    {
                        key: reservation[key]
                        for key in ("id", "inicio", "fim", "responsavel")
                    }
                    for reservation in occupied
                ],
            }
        )
    if occupied:
        return require_input(ctx, original)
    reservation = create_reservation(arguments)
    return text_result(
        {
            "reserva": reservation["id"],
            "reservado": True,
            **{key: arguments[key] for key in ("sala", "inicio", "fim", "responsavel")},
            "politica": POLICY_VERSION,
        }
    )


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Observa também requests rejeitados antes do despacho do SDK."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.method == "POST" and request.url.path == "/mcp":
            try:
                body = await request.json()
            except (ValueError, RecursionError):
                return await call_next(request)
            if isinstance(body, dict):
                params = body.get("params")
                meta = params.get("_meta") if isinstance(params, dict) else None
                logger.info(
                    "method=%s id=%s traceparent=%s",
                    body.get("method"),
                    body.get("id"),
                    meta.get("traceparent", "") if isinstance(meta, dict) else "",
                )
                if not isinstance(meta, dict) or not all(
                    key in meta
                    for key in (
                        "io.modelcontextprotocol/protocolVersion",
                        "io.modelcontextprotocol/clientCapabilities",
                    )
                ):
                    error = JSONRPCError(
                        jsonrpc="2.0",
                        id=body.get("id"),
                        error=ErrorData(
                            code=INVALID_PARAMS, message="_meta obrigatorio"
                        ),
                    )
                    return JSONResponse(
                        error.model_dump(by_alias=True), status_code=400
                    )
        return await call_next(request)


def create_app() -> Starlette:
    secret_key()
    server = Server(
        "Central de Salas MCP",
        version="1.0.0",
        on_list_tools=list_tools,
        on_call_tool=call_tool,
        on_list_resources=list_resources,
        on_read_resource=read_resource,
        get_tool_input_schema=lambda name: (
            TOOLS_BY_NAME[name].input_schema if name in TOOLS_BY_NAME else None
        ),
    )
    app = server.streamable_http_app(json_response=True, stateless_http=True)
    app.add_middleware(RequestLoggingMiddleware)
    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    uvicorn.run(
        create_app(),
        host="127.0.0.1",
        port=int(os.environ.get("MCP_PORT", str(MCP_PORT))),
        access_log=False,
    )
