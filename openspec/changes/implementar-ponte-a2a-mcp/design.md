## Context

O repositório contém apenas dados estáticos, contratos wire e um validador. A entrega precisa adicionar dois processos independentes: um servidor MCP Streamable HTTP e um agente que atua simultaneamente como cliente MCP e servidor A2A. O ponto arquitetural central é preservar uma operação interrompida entre protocolos stateless, sem callback, sessão compartilhada ou regra de negócio duplicada no agente.

A implementação será em Python 3.10+, com o SDK oficial `mcp` alinhado à revisão `2026-07-28`. O binding A2A v1.0 será uma camada JSON-RPC HTTP determinística. `dados/`, `validador/` e `exemplos/` são contratos somente de leitura.

## Goals / Non-Goals

**Goals:**

- Executar servidor MCP e agente A2A como processos separados nas portas e rotas previstas.
- Implementar os contratos MCP de tools, resource, metadados, erros e MRTR.
- Manter as regras de salas exclusivamente no processo MCP.
- Fazer a Task A2A representar corretamente sucesso, falha, pausa, retomada e recusa.
- Proteger a integridade e a validade temporal do `requestState`, mantendo-o autocontido para sobreviver ao restart do servidor MCP.
- Propagar o trace-id A2A até o stderr do servidor MCP.
- Passar as 36 verificações automatizadas e o roteiro manual de restart e logs.

**Non-Goals:**

- Banco de dados, ORM, camada de serviços pesada ou persistência após restart.
- LLM, interpretação livre de linguagem natural ou comportamento não determinístico.
- Autenticação, autorização, OAuth ou assinatura do Agent Card.
- Streaming, SSE, push notification, subscriptions ou progress.
- Interface gráfica, container, compose, deploy, gateway ou instrumentação OpenTelemetry completa.
- Concorrência transacional para reservas simultâneas.

## Decisions

### 1. Dois pacotes Python e comunicação HTTP real

`servidor-mcp/` e `agente/` terão pontos de entrada e dependências travadas. O agente chamará `http://localhost:7301/mcp` por HTTP; nenhuma função de domínio será importada entre processos. Isso preserva as fronteiras dos protocolos e permite validar headers, metadados e serialização reais.

Alternativa considerada: compartilhar um módulo de domínio ou chamar a tool em processo. Foi rejeitada porque elimina a fronteira MCP que o desafio avalia.

### 2. Servidor MCP dividido por responsabilidade

O servidor será organizado em um adaptador HTTP/MCP, um módulo pequeno de domínio e um módulo de `requestState`. O adaptador valida `_meta` e a coerência dos headers antes de despachar, registra `method`, `id` e `traceparent` no stderr e converte falhas para o tipo correto de erro. O domínio carrega as salas e reservas iniciais, mantém apenas reservas novas em memória e concentra política, conflitos e ordenação de alternativas.

As validações de intervalo serão aplicadas na ordem determinística: existência da sala, intervalo positivo, janela de uso e duração máxima. Os datetimes precisam conter offset e serão convertidos para São Paulo (-03:00); início e fim devem pertencer ao mesmo dia, entre 08:00 e 20:00. O conflito será definido por `inicio < fim_existente` e `fim > inicio_existente`.

Alternativa considerada: usar banco ou repository abstrato. Foi rejeitada por aumentar o escopo sem melhorar os contratos avaliados.

### 3. `requestState` autocontido e assinado

O payload selado conterá versão do formato, nome da tool, argumentos originais, chave do `inputRequest`, alternativas permitidas, instante de emissão e expiração. Ele será serializado como JSON canônico UTF-8 e codificado em base64url. A assinatura será `HMAC-SHA256(secret, "v1." + payload_codificado)`, também em base64url, formando um token `v1.payload.assinatura`. O prefixo deve ser validado e faz parte da assinatura.

`REQUEST_STATE_SECRET` será obrigatório. O formato documentado será hexadecimal, gerado por `secrets.token_hex(32)`; o processo decodificará e recusará inicialização se houver menos de 32 bytes. A verificação usará comparação em tempo constante, validará formato, assinatura, expiração de 15 minutos, tool e chave de resposta antes de usar o payload. O servidor reconstruirá a operação dos valores selados e rejeitará argumentos adulterados do retry.

Reservas continuam em memória, mas nenhuma informação da pausa depende dessa memória. Assim, mantendo o mesmo segredo no ambiente, um retry válido funciona após restart do processo MCP.

Alternativa considerada: JSON apenas em base64. Foi rejeitada porque não detecta adulteração. AEAD também seria válido, mas HMAC é suficiente porque confidencialidade não é requisito e o agente deve tratar o token como opaco mesmo que o conteúdo seja legível.

### 4. Cliente MCP explícito no agente

O agente terá um cliente que gera ids JSON-RPC novos por request, sempre envia `_meta` com a versão e `clientCapabilities`, espelha `MCP-Protocol-Version`, `Mcp-Method` e `Mcp-Name` nos headers aplicáveis e preserva o trace-id recebido. A inicialização lógica, feita antes do primeiro `tools/call`, executará `tools/list` e `resources/read` para descobrir as tools e extrair a versão da primeira linha de `politica://uso`.

O agente validará que `reservar_sala` foi descoberta e consumirá seu schema de entrada, sem codificar uma lista local de tools nem regras de salas. O host usa `Client` do SDK v2 e chama `client.session.call_tool(..., allow_input_required=True)` para receber o MRTR cru. O SDK infere a capability de elicitation pelo registro de um handler; o handler registrado apenas recusa chamadas de back-channel e nunca responde à escolha no caminho MRTR. Cada pergunta é devolvida ao cliente A2A.

Alternativa considerada: declarar tools localmente ou responder à elicitation dentro do cliente MCP. Foi rejeitada porque impediria descoberta em runtime e faria a pausa desaparecer antes de chegar ao A2A.

### 5. Repositório de Tasks em memória e máquina de estados

O agente manterá um dicionário indexado por `taskId`. Cada registro conterá `contextId`, status, mensagens, artifacts e, somente enquanto pausado, um contexto interno com `requestState`, chave da elicitation, alternativas, argumentos originais e trace context. Esses campos internos nunca entram na serialização A2A.

Um novo pedido passa por `TASK_STATE_SUBMITTED` e `TASK_STATE_WORKING`. Resultado MCP completo com sucesso gera artifact `reserva` e `TASK_STATE_COMPLETED`; `isError` gera `TASK_STATE_FAILED`; MRTR gera `TASK_STATE_INPUT_REQUIRED`. Estados terminais são imutáveis. A sincronização será simples e local ao processo, suficiente para o escopo sem requisito de corrida de escrita.

Alternativa considerada: persistir Tasks em arquivo ou banco. Foi rejeitada porque restart do agente não faz parte do contrato e ampliaria o domínio.

### 6. Ponte concentrada em dois pontos de código

O ponto de entrada será `agente/src/agente/bridge.py`. A função que processa o resultado de `tools/call` detectará `resultType == "input_required"`, extrairá a única elicitation, armazenará o contexto interno por Task e publicará apenas `alternativas: <ids>` em `TASK_STATE_INPUT_REQUIRED`.

A função de continuação do mesmo módulo validará `escolha=<valor>` contra as alternativas guardadas. Para escolha aceita, montará `inputResponses` com a mesma chave, `action: accept` e a sala; para `recusar`, usará `action: decline`. Em ambos os casos, reutilizará o `requestState` byte a byte, mas o cliente MCP atribuirá um novo id JSON-RPC. Escolha inválida apenas republica a pausa, sem chamar o MCP.

A tradução do resultado será única para a chamada inicial e todos os retries. Se uma alternativa for ocupada depois da pausa, o servidor recalcula as opções e a Task volta a `INPUT_REQUIRED`, sem criar um artifact de reserva inexistente. O trace original fica associado à Task e é reutilizado mesmo quando a continuação não envia header. O transporte ASGI permite consultar `GetTask` enquanto a chamada MCP aguarda.

Alternativa considerada: interpretar ou reconstruir `requestState` no agente. Foi rejeitada porque viola a opacidade e acopla o agente ao estado interno do servidor.

### 7. A2A v1.0 enxuto e orientado pelos exemplos wire

Uma aplicação ASGI atenderá `GET /.well-known/agent-card.json` e `POST /a2a`. O dispatcher JSON-RPC implementará apenas `SendMessage` e `GetTask`, com estruturas v1.0 iguais aos exemplos. O parser aceitará exclusivamente os formatos fixos do enunciado, sem LLM. Dependências HTTP/ASGI e o SDK MCP terão versões exatas no arquivo de projeto.

Alternativa considerada: adicionar um framework completo de agentes. Foi rejeitada porque o escopo exige somente duas operações A2A e controle direto da pausa.

## Risks / Trade-offs

- [Divergência entre a API do SDK e a revisão MCP exigida] -> Isolar o SDK no adaptador, conferir os exemplos wire e validar cada resposta contra `validador/validar.py`.
- [Vazamento acidental de `requestState`] -> Separar o modelo interno de Task do serializador público e adicionar busca automatizada do token nas respostas A2A.
- [Reuso incorreto de id no retry] -> Centralizar a geração monotonicamente única/aleatória de ids no cliente MCP e nunca armazenar o id inicial como parte retomável.
- [Argumentos do retry substituírem o pedido selado] -> Reconstruir a reserva somente do payload HMAC validado.
- [Segredo fraco ou ausente] -> Falhar na inicialização com mensagem clara e documentar a geração de 32 bytes aleatórios.
- [Estado em memória perdido] -> Aceitar perda de Tasks e reservas após restart conforme o escopo; preservar apenas a retomada MCP por meio do `requestState` autocontido.
- [Execuções repetidas do validador alterarem reservas] -> Documentar e automatizar a subida com processos recém-iniciados para cada execução.

## Migration Plan

1. Criar os pacotes Python e travar dependências sem alterar os contratos fornecidos.
2. Entregar e validar primeiro o servidor MCP, incluindo restart entre pausa e retry.
3. Entregar o cliente MCP e depois a superfície A2A.
4. Ativar a ponte e validar Tasks simultaneamente pausadas, trace propagation e ausência de vazamento.
5. Substituir o README somente quando os comandos tiverem sido executados a partir de ambiente limpo e colar a saída final do validador.

Rollback consiste em remover os novos diretórios de aplicação e restaurar o README do starter; não há migração de dados nem estado persistente.

## Open Questions

Nenhuma decisão funcional está aberta. Nomes exatos de APIs internas do SDK podem variar com a versão travada e serão resolvidos no adaptador sem alterar as capacidades especificadas.
