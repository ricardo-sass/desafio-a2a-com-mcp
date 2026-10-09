## ADDED Requirements

### Requirement: Tradução da pausa MCP para A2A
Ao receber `resultType: input_required`, o agente MUST colocar a Task correspondente em `TASK_STATE_INPUT_REQUIRED` e MUST expor somente as alternativas da elicitation.

#### Scenario: Pausa com alternativas
- **WHEN** o MCP devolve uma elicitation com alternativas ordenadas
- **THEN** a mensagem de status da Task é exatamente `alternativas: <ids separados por virgula e espaco>` na mesma ordem do schema

#### Scenario: RequestState permanece interno
- **WHEN** uma Task é serializada no Agent Card, em `SendMessage` ou em `GetTask`
- **THEN** nenhuma mensagem, status ou artifact contém o `requestState`

### Requirement: Contexto de retomada opaco por Task
Enquanto uma Task estiver pausada, o agente MUST guardar internamente a chave de `inputRequests`, as alternativas e o `requestState` associados exclusivamente ao `taskId`, e MUST tratar `requestState` como bytes opacos.

#### Scenario: Duas pausas simultâneas
- **WHEN** duas Tasks recebem `input_required` com estados diferentes e depois são retomadas
- **THEN** cada retry usa sua própria chave e seu próprio `requestState`, produzindo reservas distintas com os dados originais corretos

### Requirement: Validação local da escolha
Uma continuação MUST usar o formato `escolha=<valor>` e o agente MUST validar o valor contra as alternativas guardadas antes de chamar o MCP.

#### Scenario: Escolha fora do enum
- **WHEN** o cliente escolhe uma sala que não foi oferecida
- **THEN** a Task permanece em `TASK_STATE_INPUT_REQUIRED`, repete a mesma linha de alternativas e nenhum retry MCP é enviado

#### Scenario: Escolha válida
- **WHEN** o cliente escolhe uma sala oferecida
- **THEN** o agente move a Task para trabalho e prepara uma resposta de elicitation com `action: accept` e `content.sala` igual à escolha

#### Scenario: Recusa explícita
- **WHEN** o cliente envia `escolha=recusar`
- **THEN** o agente prepara uma resposta de elicitation com `action: decline`

### Requirement: Retry MCP independente
O retry MUST ser um novo `tools/call`, com id JSON-RPC diferente do request inicial, a mesma chave de `inputRequests`, os argumentos originais, `inputResponses` e o `requestState` ecoado sem modificação.

#### Scenario: Retomada aceita
- **WHEN** o MCP conclui o retry aceito com uma reserva
- **THEN** a Task termina em `TASK_STATE_COMPLETED` e publica o artifact `reserva` para a sala escolhida

#### Scenario: Retomada recusada
- **WHEN** o MCP conclui um retry recusado com `reservado: false`
- **THEN** a Task termina em `TASK_STATE_CANCELED` sem artifact de reserva criada

### Requirement: Propagação de trace context
O agente MUST propagar para todos os requests MCP de uma Task o `traceparent` recebido no request A2A, preservando exatamente o trace-id e podendo gerar um novo span-id válido.

#### Scenario: Trace do cliente chega ao MCP
- **WHEN** `SendMessage` contém um header `traceparent`
- **THEN** `tools/list`, `resources/read` e `tools/call` executados no contexto da Task carregam `_meta.traceparent` com o mesmo trace-id, que aparece no stderr do servidor MCP

#### Scenario: Trace na continuação
- **WHEN** uma continuação de Task chega com ou sem `traceparent`
- **THEN** o retry MCP preserva o trace-id original da Task; se ela ainda não tem trace, adota o da continuação sem alterar o isolamento do estado pausado

#### Scenario: Nova pausa no retry
- **WHEN** a alternativa escolhida foi ocupada depois da pausa e o MCP devolve outro `input_required`
- **THEN** o agente atualiza apenas o contexto interno daquela Task, repete as novas alternativas e mantém `TASK_STATE_INPUT_REQUIRED`, sem produzir artifact de sucesso

### Requirement: Fronteira de responsabilidades
O agente MUST traduzir estados e envelopes de protocolo, mas não MUST recalcular conflitos, política, capacidade ou alternativas de salas.

#### Scenario: Decisão de domínio permanece no servidor
- **WHEN** uma reserva encontra conflito ou violação de política
- **THEN** o estado A2A deriva exclusivamente do resultado MCP e não de uma regra de sala duplicada no agente
