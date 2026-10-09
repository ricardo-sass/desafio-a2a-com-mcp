"""Host MCP: descoberta pelo SDK e uma rodada explícita por chamada."""

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import jsonschema
from mcp import Client
from mcp.client import ClientRequestContext
from mcp.types import (
    CallToolResult,
    ElicitRequestParams,
    ElicitResult,
    InputRequiredResult,
    InputResponses,
    RequestParamsMeta,
    Tool,
)

PROTOCOL_VERSION = "2026-07-28"


async def reject_backchannel(
    context: ClientRequestContext, params: ElicitRequestParams
) -> ElicitResult:
    """Declara suporte a elicitation, sem responder perguntas automaticamente.

    O SDK infere a capability a partir do registro deste handler. As chamadas
    abaixo usam a sessão com allow_input_required=True, portanto MRTR nunca
    invoca este handler: a pergunta sempre volta para a Task A2A.
    """
    raise RuntimeError("A escolha deve chegar pela continuação da Task A2A")


class MCP:
    def __init__(self, url: str | None = None) -> None:
        self.url = url or os.environ.get("MCP_URL", "http://127.0.0.1:7301/mcp")
        self.client: Client | None = None
        self.tools: dict[str, Tool] = {}
        self.reservation_tool: Tool | None = None
        self.policy = ""
        self._discovery_lock = asyncio.Lock()

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[None]:
        async with Client(
            self.url,
            mode=PROTOCOL_VERSION,
            elicitation_callback=reject_backchannel,
            read_timeout_seconds=20,
        ) as client:
            self.client = client
            try:
                yield
            finally:
                self.client = None

    @staticmethod
    def meta(trace: str | None) -> RequestParamsMeta:
        return {"traceparent": trace} if trace else {}

    async def discover(self, trace: str | None) -> None:
        if self.reservation_tool is not None:
            return
        async with self._discovery_lock:
            if self.reservation_tool is not None:
                return
            if self.client is None:
                raise RuntimeError("Cliente MCP não conectado")
            listing = await self.client.list_tools(meta=self.meta(trace))
            tools = {tool.name: tool for tool in listing.tools}
            tool = tools.get("reservar_sala")
            if tool is None:
                raise ValueError("O servidor MCP não publicou a tool de reserva")
            resource = await self.client.read_resource(
                "politica://uso", meta=self.meta(trace)
            )
            texts = [
                content.text
                for content in resource.contents
                if hasattr(content, "text")
            ]
            first_line = "".join(texts).splitlines()[0]
            prefix, version = first_line.split(":", 1)
            if prefix != "versao" or not version.strip():
                raise ValueError("Resource de política sem versão")
            self.tools = tools
            self.policy = version.strip()
            self.reservation_tool = tool

    async def call(
        self,
        arguments: dict[str, Any],
        trace: str | None = None,
        *,
        input_responses: InputResponses | None = None,
        request_state: str | None = None,
    ) -> CallToolResult | InputRequiredResult:
        await self.discover(trace)
        if self.client is None or self.reservation_tool is None:
            raise RuntimeError("Cliente MCP não conectado")
        jsonschema.validate(arguments, self.reservation_tool.input_schema)
        # O cliente de alto nível executaria o loop de elicitation sozinho.
        # A sessão retorna a rodada crua para que a ponte pause a Task.
        return await self.client.session.call_tool(
            self.reservation_tool.name,
            arguments,
            input_responses=input_responses,
            request_state=request_state,
            meta=self.meta(trace),
            allow_input_required=True,
        )
