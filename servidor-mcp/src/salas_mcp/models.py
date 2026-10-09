"""Modelos tipados do domínio MCP."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Reservation:
    id: str
    sala: str
    inicio: str
    fim: str
    responsavel: str
