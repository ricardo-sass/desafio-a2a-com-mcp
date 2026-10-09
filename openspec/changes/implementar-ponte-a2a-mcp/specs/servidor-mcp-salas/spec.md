## ADDED Requirements

### Requirement: Endpoint MCP stateless
O servidor MUST expor Streamable HTTP em `POST /mcp` na porta 7301 e MUST declarar as capabilities de tools e resources sem inferir metadados de requests anteriores.

#### Scenario: Descoberta das tools
- **WHEN** um cliente envia `tools/list` com metadados e headers válidos
- **THEN** o servidor retorna `listar_salas`, `consultar_disponibilidade` e `reservar_sala`, cada uma com `inputSchema` de tipo `object`

#### Scenario: Metadado obrigatório ausente
- **WHEN** um request omite `io.modelcontextprotocol/protocolVersion` ou `io.modelcontextprotocol/clientCapabilities` de `_meta`
- **THEN** o servidor retorna erro JSON-RPC `-32602` e HTTP 400

#### Scenario: Header diverge do corpo
- **WHEN** `MCP-Protocol-Version`, `Mcp-Method` ou um `Mcp-Name` aplicável diverge do corpo JSON-RPC
- **THEN** o servidor retorna erro JSON-RPC `-32020`

#### Scenario: Tool desconhecida
- **WHEN** o cliente chama uma tool não publicada
- **THEN** o servidor recusa a chamada com erro `-32602` ou resultado com `isError: true`

### Requirement: Registro observável de requests
O servidor MUST registrar no stderr cada request recebido com método, id e o valor de `traceparent` quando presente em `_meta`.

#### Scenario: Request com trace context
- **WHEN** um request MCP contém `traceparent` em `_meta`
- **THEN** o stderr contém o método, o id e o mesmo trace-id desse `traceparent`

### Requirement: Listagem estruturada de salas
`listar_salas` MUST devolver todas as salas de `dados/salas.json` em `structuredContent` conforme seu `outputSchema` e MUST incluir o mesmo objeto serializado como JSON em um bloco de texto.

#### Scenario: Listagem compatível
- **WHEN** o cliente chama `listar_salas` sem argumentos
- **THEN** o JSON do bloco de texto é idêntico ao `structuredContent` e contém as cinco salas fornecidas

### Requirement: Consulta de disponibilidade
`consultar_disponibilidade` MUST receber `sala`, `inicio` e `fim`, aplicar a política de uso e retornar em `structuredContent` se o intervalo está livre e as reservas conflitantes quando ocupado.

#### Scenario: Intervalo livre
- **WHEN** a sala existe e o intervalo válido não sobrepõe reserva alguma
- **THEN** a tool conclui sem `isError` e informa que o intervalo está livre

#### Scenario: Intervalo ocupado
- **WHEN** a sala existe e o intervalo válido sobrepõe uma ou mais reservas
- **THEN** a tool conclui sem `isError`, informa indisponibilidade e lista as reservas conflitantes

### Requirement: Validações de negócio com mensagens estáveis
As tools de consulta e reserva MUST aplicar as mesmas validações de sala e política e MUST representar violações como resultado `complete` com `isError: true`.

#### Scenario: Sala inexistente
- **WHEN** uma tool recebe um id de sala desconhecido
- **THEN** o conteúdo inclui exatamente `Sala inexistente: <id informado>`

#### Scenario: Intervalo vazio ou invertido
- **WHEN** `fim` é menor ou igual a `inicio`
- **THEN** o conteúdo inclui exatamente `Intervalo invalido: fim deve ser posterior a inicio`

#### Scenario: Fora da janela de uso
- **WHEN** o início ou o fim fica fora do período entre 08:00 e 20:00 no offset de São Paulo
- **THEN** o conteúdo inclui exatamente `Fora da janela de uso: a politica permite reservas entre 08:00 e 20:00`

#### Scenario: Duração excedida
- **WHEN** o intervalo dura mais de duas horas
- **THEN** o conteúdo inclui exatamente `Duracao acima do limite: a politica permite no maximo 2 horas`

### Requirement: Criação de reserva livre
`reservar_sala` MUST criar uma reserva em memória quando o intervalo for válido e livre, tornando-a visível a consultas seguintes do mesmo processo.

#### Scenario: Reserva concluída
- **WHEN** uma reserva válida não encontra conflito
- **THEN** o resultado é `complete`, não possui `isError: true` e o `structuredContent` contém `reserva`, `reservado`, `sala`, `inicio`, `fim`, `responsavel` e `politica`

#### Scenario: Consulta posterior
- **WHEN** a disponibilidade do mesmo intervalo é consultada depois da criação
- **THEN** a reserva criada aparece como conflito durante a vida do processo

### Requirement: Resource da política
O servidor MUST publicar `politica://uso` com o texto de `dados/politica-de-uso.md` e `mimeType` `text/markdown`.

#### Scenario: Leitura da política
- **WHEN** o cliente envia `resources/read` para `politica://uso`
- **THEN** o conteúdo retornado inclui `versao: 2026-11-01`

#### Scenario: URI inexistente
- **WHEN** o cliente solicita um resource não publicado
- **THEN** o servidor retorna erro JSON-RPC `-32602` e não retorna `contents` vazio como sucesso

### Requirement: Pausa MRTR com alternativas determinísticas
Quando a sala pedida estiver ocupada, `reservar_sala` MUST calcular salas livres no intervalo com capacidade maior ou igual, limitar a três e ordenar por capacidade crescente e depois por id.

#### Scenario: Conflito com alternativas
- **WHEN** a reserva encontra ao menos uma alternativa e o cliente declarou `elicitation.form`
- **THEN** o resultado tem `resultType: input_required`, exatamente um `inputRequests`, elicitation `form`, schema plano que restringe `sala` às alternativas ordenadas e um `requestState`

#### Scenario: Capability de elicitation ausente
- **WHEN** a reserva precisaria pausar e o request não declara `elicitation.form`
- **THEN** o servidor retorna erro `-32021`, HTTP 400 e `data.requiredCapabilities`

#### Scenario: Nenhuma alternativa
- **WHEN** a sala está ocupada e nenhuma sala atende à regra de alternativas
- **THEN** a tool conclui com `isError: true` e o texto `Sem alternativas disponiveis no intervalo`

### Requirement: RequestState íntegro e autocontido
O `requestState` MUST carregar tudo que permite reconstruir o pedido, MUST expirar em 15 minutos e MUST ser protegido por HMAC-SHA256 com segredo de ao menos 32 bytes fornecido exclusivamente por `REQUEST_STATE_SECRET`.

#### Scenario: Estado adulterado
- **WHEN** qualquer parte do `requestState` é alterada antes do retry
- **THEN** o servidor rejeita o request com erro JSON-RPC `-32602`

#### Scenario: Estado expirado
- **WHEN** o retry apresenta um `requestState` depois da expiração
- **THEN** o servidor rejeita o request com erro JSON-RPC `-32602`

#### Scenario: Retry após restart
- **WHEN** o servidor reinicia com o mesmo `REQUEST_STATE_SECRET` entre a pausa e o retry
- **THEN** um `requestState` ainda válido permite concluir a operação sem estado de pausa em memória

#### Scenario: Argumentos adulterados no retry
- **WHEN** os argumentos reenviados divergem dos valores protegidos
- **THEN** o servidor rejeita a divergência ou usa exclusivamente os valores selados, sem produzir reserva com os valores adulterados

### Requirement: Conclusão de MRTR
No retry, o servidor MUST ler `inputResponses` e `requestState` de `params`, validar a chave da resposta e concluir conforme a ação recebida.

#### Scenario: Alternativa aceita
- **WHEN** `action` é `accept` e a sala pertence ao schema oferecido
- **THEN** o servidor cria a reserva alternativa e retorna resultado `complete` com `reservado: true`

#### Scenario: Usuário recusa
- **WHEN** `action` é `decline` ou `cancel`
- **THEN** o servidor retorna resultado `complete`, sem `isError: true`, com `reservado: false` e um motivo, sem criar reserva
