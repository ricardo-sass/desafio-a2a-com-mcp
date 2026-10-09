## ADDED Requirements

### Requirement: Agent Card A2A v1.0
O agente MUST publicar um Agent Card válido em `GET /.well-known/agent-card.json` com sua identidade, capabilities, interface JSON-RPC e skill de reserva.

#### Scenario: Descoberta do agente
- **WHEN** um cliente busca o well-known na porta 7300
- **THEN** recebe HTTP 200 com `supportedInterfaces` contendo URL de `/a2a`, `protocolBinding` JSON-RPC, `protocolVersion` iniciada por `1.0` e uma skill com id `reservar-sala`

### Requirement: Operações A2A JSON-RPC
O endpoint `POST /a2a` MUST implementar `SendMessage` e `GetTask` no binding JSON-RPC 2.0 da A2A v1.0.

#### Scenario: Criação de Task
- **WHEN** `SendMessage` recebe uma mensagem sem `taskId`
- **THEN** o agente cria uma Task com `id` e `contextId` próprios e a faz transitar por `TASK_STATE_SUBMITTED` e `TASK_STATE_WORKING`

#### Scenario: Consulta de Task
- **WHEN** `GetTask` recebe o id de uma Task conhecida
- **THEN** devolve o mesmo `id`, seu `contextId`, status corrente, mensagens e artifacts existentes

#### Scenario: Task terminal
- **WHEN** `SendMessage` referencia uma Task `COMPLETED`, `CANCELED` ou `FAILED`
- **THEN** o agente retorna erro JSON-RPC e não altera a Task

### Requirement: Interpretação determinística do pedido
O agente MUST aceitar pedidos no formato fixo `reservar sala=<id> inicio=<iso8601> fim=<iso8601> responsavel=<nome>` e MUST tomar decisões por regras, sem LLM.

#### Scenario: Mesmo pedido repetido
- **WHEN** duas novas Tasks recebem o mesmo pedido sob o mesmo estado de reservas
- **THEN** o agente produz o mesmo resultado observável, inclusive a mesma mensagem de alternativas quando houver pausa

### Requirement: Descoberta MCP em runtime
Antes do primeiro `tools/call`, o agente MUST executar `tools/list`, descobrir `reservar_sala` sem lista fixa e ler `politica://uso` para extrair a versão da primeira linha.

#### Scenario: Inicialização do host MCP
- **WHEN** o primeiro pedido A2A exige uma chamada de tool
- **THEN** o log do servidor MCP mostra `tools/list` antes do primeiro `tools/call` e uma leitura do resource de política

### Requirement: Requests MCP conformes
Todo request MCP emitido pelo agente MUST conter `_meta` com `io.modelcontextprotocol/protocolVersion` igual a `2026-07-28` e `io.modelcontextprotocol/clientCapabilities` declarando `{"elicitation":{"form":{}}}`.

#### Scenario: Headers espelhados
- **WHEN** o agente envia um request MCP
- **THEN** envia `MCP-Protocol-Version` e `Mcp-Method` coerentes com o corpo e, para `tools/call` e `resources/read`, `Mcp-Name` coerente

#### Scenario: Cliente sem callback de elicitation
- **WHEN** `reservar_sala` devolve `input_required`
- **THEN** o agente recebe o resultado MRTR cru em vez de responder automaticamente à elicitation

### Requirement: Conclusão A2A com artifact
Quando a tool conclui uma reserva, o agente MUST finalizar a Task em `TASK_STATE_COMPLETED` com um artifact chamado `reserva`.

#### Scenario: Reserva livre
- **WHEN** `reservar_sala` retorna uma reserva criada sem pausa
- **THEN** o artifact contém JSON com `reserva`, `sala`, `inicio`, `fim`, `responsavel` e `politica` igual à versão lida do resource

### Requirement: Falha de negócio visível
Quando uma tool retorna `isError: true`, o agente MUST finalizar a Task em `TASK_STATE_FAILED` e MUST preservar a mensagem da tool no histórico/status público.

#### Scenario: Sala inexistente
- **WHEN** o pedido A2A informa `sala-delorean`
- **THEN** a Task termina em `TASK_STATE_FAILED` com `Sala inexistente: sala-delorean` visível na mensagem de status

### Requirement: Estado local de Tasks
O agente MUST armazenar Tasks em memória, isoladas por `taskId`, durante a vida do processo e não MUST prometer recuperação após restart.

#### Scenario: Tasks independentes
- **WHEN** duas Tasks existem ao mesmo tempo
- **THEN** `GetTask` de cada id retorna apenas o status, as mensagens e os artifacts daquela Task
