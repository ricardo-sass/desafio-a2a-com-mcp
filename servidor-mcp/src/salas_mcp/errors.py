"""Exceções específicas da camada MCP."""


class ProtocolError(ValueError):
    """Entrada inválida convertida em erro JSON-RPC."""


class RequestStateError(ProtocolError):
    """Estado ausente, adulterado, expirado ou incompatível."""


class ElicitationCapabilityError(RuntimeError):
    """Capability de elicitation form ausente."""
