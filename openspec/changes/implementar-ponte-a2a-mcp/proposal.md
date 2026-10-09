## Why

O starter define os contratos e os dados do domínio, mas ainda não possui os dois processos que demonstram a integração entre MCP e A2A. Esta mudança entrega a ponte de estado exigida pelo desafio: uma solicitação de entrada do MCP pausa uma Task A2A e pode ser retomada com segurança, sem sessão e sem expor o `requestState` ao cliente A2A.

## What Changes

- Implementar um servidor MCP Streamable HTTP na porta 7301 com as tools `listar_salas`, `consultar_disponibilidade` e `reservar_sala`, o resource `politica://uso`, validação de metadados por request e erros de protocolo e de execução conforme os contratos fornecidos.
- Implementar o ciclo MRTR de reserva, incluindo cálculo determinístico de alternativas, negociação da capability de elicitation em form mode, `requestState` autocontido com integridade e expiração, retry e recusa.
- Implementar um agente determinístico que descobre e consome o servidor MCP por HTTP e se expõe como servidor A2A v1.0 na porta 7300, com Agent Card, `SendMessage`, `GetTask` e máquina de estados de Task.
- Traduzir `input_required` do MCP em `TASK_STATE_INPUT_REQUIRED`, manter o estado interrompido isolado por Task e retomar o request MCP com novo id, `inputResponses` e o `requestState` opaco original.
- Propagar o trace-id recebido no `traceparent` A2A para todos os requests MCP da Task e registrar os metadados exigidos no stderr do servidor MCP.
- Substituir o README do starter pela documentação executável da entrega e comprovar conformidade com as 36 verificações do validador.
- Manter fora de escopo banco de dados, ORM, LLM, autenticação, autorização, streaming, interface gráfica, containers e persistência após restart.

## Capabilities

### New Capabilities

- `servidor-mcp-salas`: Exposição stateless das salas, disponibilidade, reservas e política de uso via MCP, incluindo validações, erros e MRTR protegido.
- `agente-a2a-reservas`: Descoberta e consumo do MCP por um agente determinístico exposto por A2A v1.0, com Agent Card e ciclo de vida de Tasks.
- `ponte-mrtr-a2a-mcp`: Tradução bidirecional entre a pausa MCP e a Task A2A, com isolamento de estado, retomada, recusa e propagação de trace context.

### Modified Capabilities

Nenhuma. O repositório ainda não possui especificações de capacidades existentes.

## Impact

- Novos códigos de aplicação em `servidor-mcp/` e `agente/`, executados como processos Python independentes.
- Novo ambiente Python com versões de dependências travadas e uso do SDK oficial MCP compatível com a revisão `2026-07-28`.
- Novos endpoints públicos locais: `POST /mcp`, `POST /a2a` e `GET /.well-known/agent-card.json`.
- Uso obrigatório de `REQUEST_STATE_SECRET` no processo MCP e armazenamento em memória para reservas criadas e Tasks A2A.
- Substituição do `README.md` com instruções de execução, decisões técnicas, pontos da ponte e saída integral do validador.
- Nenhuma alteração em `dados/`, `validador/` ou `exemplos/`.
