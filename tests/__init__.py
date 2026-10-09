"""Testes isolados da ponte MCP/A2A."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "servidor-mcp/src"))
sys.path.insert(0, str(ROOT / "agente/src"))
