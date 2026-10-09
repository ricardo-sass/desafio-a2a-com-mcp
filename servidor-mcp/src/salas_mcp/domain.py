"""Regras e estado em memória do domínio de salas."""

from __future__ import annotations

import json
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "dados"
SALAS: list[dict[str, Any]] = json.loads((DATA / "salas.json").read_text())
RESERVAS: list[dict[str, Any]] = json.loads((DATA / "reservas.json").read_text())
POLICY = (DATA / "politica-de-uso.md").read_text()
POLICY_VERSION = POLICY.splitlines()[0].split(":", 1)[1].strip()
SAO_PAULO = timezone(timedelta(hours=-3))


def parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError("O intervalo deve conter um offset")
    return parsed.astimezone(SAO_PAULO)


def validate_arguments(arguments: dict[str, Any]) -> str | None:
    sala = arguments.get("sala")
    if not any(room["id"] == sala for room in SALAS):
        return f"Sala inexistente: {sala}"
    try:
        inicio = parse_datetime(arguments["inicio"])
        fim = parse_datetime(arguments["fim"])
    except (KeyError, TypeError, ValueError):
        return "Intervalo invalido: fim deve ser posterior a inicio"
    if fim <= inicio:
        return "Intervalo invalido: fim deve ser posterior a inicio"
    if inicio.date() != fim.date() or inicio.time() < time(8) or fim.time() > time(20):
        return "Fora da janela de uso: a politica permite reservas entre 08:00 e 20:00"
    if fim - inicio > timedelta(hours=2):
        return "Duracao acima do limite: a politica permite no maximo 2 horas"
    return None


def alternatives(arguments: dict[str, Any]) -> list[str]:
    capacity = next(
        room["capacidade"] for room in SALAS if room["id"] == arguments["sala"]
    )
    return [
        room["id"]
        for room in sorted(SALAS, key=lambda room: (room["capacidade"], room["id"]))
        if room["capacidade"] >= capacity
        and not conflicts({**arguments, "sala": room["id"]})
    ][:3]


def conflicts(arguments: dict[str, Any]) -> list[dict[str, Any]]:
    inicio = parse_datetime(arguments["inicio"])
    fim = parse_datetime(arguments["fim"])
    return [
        reservation
        for reservation in RESERVAS
        if reservation["sala"] == arguments["sala"]
        and inicio < parse_datetime(reservation["fim"])
        and fim > parse_datetime(reservation["inicio"])
    ]


def create_reservation(arguments: dict[str, Any]) -> dict[str, Any]:
    reservation_id = f"res-{len(RESERVAS) + 1:04d}"
    reservation = {
        "id": reservation_id,
        **{key: arguments[key] for key in ("sala", "inicio", "fim", "responsavel")},
    }
    RESERVAS.append(reservation)
    return reservation
