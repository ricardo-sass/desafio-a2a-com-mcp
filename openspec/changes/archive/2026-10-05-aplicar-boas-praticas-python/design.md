## Context

Os dois processos funcionam, mas alguns módulos acumulam transporte HTTP, regras de domínio, serialização e estado. A mudança deve melhorar a manutenção sem alterar os envelopes MCP/A2A, as mensagens do contrato ou a fronteira entre agente e servidor.

## Goals / Non-Goals

**Goals:**

- Organizar responsabilidades em módulos pequenos e testáveis.
- Usar type hints, dataclasses e exceções específicas.
- Automatizar formatação, lint, testes e checagem de tipos.
- Manter o `requestState` opaco no agente e assinado no MCP.

**Non-Goals:**

- Alterar endpoints, wire protocol ou regras de salas.
- Introduzir banco, ORM, persistência, LLM, autenticação ou streaming.

## Decisions

1. **Módulos por responsabilidade.** Separar domínio, protocolo HTTP, codec de estado e ponte. Isso reduz acoplamento; um framework completo foi descartado por ser desnecessário.
2. **Modelos tipados.** Usar `dataclass` para entidades internas e `TypedDict`/tipos de retorno para envelopes. Isso melhora revisão e IDE sem modificar o JSON público.
3. **Exceções específicas.** Mapear erros de validação, protocolo e estado para códigos nos adaptadores HTTP. Isso evita `except Exception` amplo; a alternativa de retornar strings foi descartada por perder contexto.
4. **Tooling no `pyproject.toml`.** Configurar Black, Ruff, Pytest e mypy em um ponto único. Ferramentas separadas por arquivo foram descartadas por duplicarem configuração.
5. **Dependências mínimas.** Manter apenas dependências efetivamente usadas em runtime e separar extras de desenvolvimento. Isso reduz superfície de instalação sem remover o SDK MCP declarado pelo projeto.
6. **Logging seguro.** Usar logger configurado para stderr com método, id e traceparent, excluindo requestState. Logs estruturados foram escolhidos para facilitar diagnóstico sem expor estado sensível.

## Risks / Trade-offs

- [Refatoração alterar o wire] → Executar o validador 36/36 antes e depois.
- [Tipagem incompleta em envelopes dinâmicos] → Manter tipos internos fortes e validação de fronteira.
- [Ferramentas indisponíveis em instalação limpa] → Declarar extras de desenvolvimento e documentar comando único.
- [Logs conterem dados sensíveis] → Teste que verifica ausência de `requestState` nos logs públicos.

## Migration Plan

1. Criar testes de caracterização e configuração de qualidade.
2. Extrair codec, domínio e modelos sem alterar os adaptadores.
3. Refatorar ponte e servidor por etapas, executando o validador após cada etapa.
4. Atualizar README e executar em ambiente limpo.

Rollback: restaurar os módulos anteriores; não há migração de dados.

## Open Questions

Nenhuma.
