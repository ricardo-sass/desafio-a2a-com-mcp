## Why

A implementação funcional passou pelo validador, mas ainda concentra transporte, domínio, estado e serialização em módulos compactos, com pouca tipagem e cobertura automatizada. Esta mudança reduz o custo de manutenção e torna falhas de protocolo mais fáceis de diagnosticar sem alterar o comportamento MCP/A2A.

## What Changes

- Separar transporte HTTP, domínio de salas, codec de `requestState`, cliente MCP e ponte A2A em módulos com responsabilidades claras.
- Adicionar type hints, dataclasses e exceções específicas nos fluxos principais.
- Centralizar constantes e mensagens de erro do contrato.
- Adicionar testes unitários para validações, HMAC, parser e estados de Task, incluindo retry após restart.
- Configurar `pyproject.toml` com Black, Ruff, Pytest e checagem de tipos.
- Remover dependências declaradas que não são usadas pelo runtime e documentar as dependências efetivas.
- Melhorar logging estruturado sem expor `requestState` nas respostas A2A.
- Manter os contratos wire, as portas e o resultado de 36/36 verificações inalterados.

## Capabilities

### New Capabilities

- `qualidade-e-manutencao-python`: padrões de organização, tipagem, testes e ferramentas automatizadas para os processos MCP/A2A.

### Modified Capabilities

Nenhuma. A mudança é de qualidade interna e não altera requisitos wire.

## Impact

- Afeta os códigos em `servidor-mcp/`, `agente/` e `tests/`.
- Adiciona configuração de desenvolvimento em `pyproject.toml` e possivelmente dependências de teste/lint.
- Não altera `dados/`, `validador/` ou `exemplos/`.
- Não adiciona banco de dados, ORM, LLM, autenticação, UI ou persistência das Tasks.
