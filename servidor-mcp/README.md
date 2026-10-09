# Servidor MCP

Na raiz do repositório, instale as dependências e execute:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r servidor-mcp/requirements.txt
export REQUEST_STATE_SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
.venv/bin/python servidor-mcp/run.py
```

O SDK oficial MCP v2 publica o endpoint Streamable HTTP em `http://127.0.0.1:7301/mcp`.
Mantenha o mesmo segredo ao reiniciar o processo para retomar um `requestState` já emitido.
Consulte o README da raiz para subir o agente e executar a validação completa.
