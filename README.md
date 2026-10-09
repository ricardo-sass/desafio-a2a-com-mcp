# A Ponte: um agente A2A com MCP por dentro

Implementação determinística do [desafio A2A com MCP](https://github.com/devfullcycle/desafio-a2a-com-mcp): dois processos Python, SDK oficial MCP v2 (`mcp==2.3.0`, revisão `2026-07-28`) e A2A v1.0 com JSON-RPC sobre HTTP. Não utiliza LLM.

## Como rodar

A partir da raiz do repositório, com Python 3.10 ou superior:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r servidor-mcp/requirements.txt -r agente/requirements.txt
```

Terminal 1 — gerar e exportar o segredo, depois iniciar o MCP:

```bash
export REQUEST_STATE_SECRET=$(.venv/bin/python -c 'import secrets; print(secrets.token_hex(32))')
.venv/bin/python servidor-mcp/run.py
```

O segredo deve conter pelo menos 32 bytes, codificados em hexadecimal. Preserve o mesmo valor ao reiniciar o MCP para que um `requestState` emitido antes do reinício continue válido. Não publique o valor do segredo.

Terminal 2 — iniciar o agente, depois que o MCP estiver pronto:

```bash
.venv/bin/python agente/run.py
```

Terminal 3 — executar o validador com ambos os processos recém-iniciados:

```bash
.venv/bin/python validador/validar.py --agente http://localhost:7300 --mcp http://localhost:7301
```

O MCP atende em `http://localhost:7301/mcp`; o agente em `http://localhost:7300/a2a`, com Agent Card em `http://localhost:7300/.well-known/agent-card.json`. Os pontos de entrada configuram seus pacotes automaticamente, sem exigir `PYTHONPATH`.

As variáveis opcionais são `MCP_PORT` (7301), `A2A_PORT` (7300), `MCP_URL` (URL do MCP consumido pelo agente) e `A2A_URL` (URL pública do endpoint A2A publicada no card). Ambos os processos escutam em `127.0.0.1`.

Os pedidos usam o formato fixo abaixo; a continuação envia `escolha=<id>` ou `escolha=recusar` na mesma Task:

```text
reservar sala=sala-garagem inicio=2026-11-03T14:00:00-03:00 fim=2026-11-03T15:00:00-03:00 responsavel=Marty
escolha=sala-mirante
```

Reservas e Tasks ficam em memória. Antes de repetir o validador, interrompa os dois processos com Ctrl+C e inicie-os novamente para restaurar os dados iniciais.

## Onde a ponte acontece

Em `agente/src/agente/bridge.py`, `Bridge.apply_result` traduz o `InputRequiredResult` do MCP em `TASK_STATE_INPUT_REQUIRED`, publica a linha de alternativas e guarda a chave da pergunta, as alternativas e o `requestState` opaco no contexto interno da Task. `Bridge.send` recebe a continuação, valida a escolha e chama novamente o MCP com os argumentos originais, a mesma chave em `inputResponses` e o token inalterado. O SDK atribui um novo id ao request. O resultado da retomada passa pelo mesmo tratamento, permitindo uma nova pausa se a alternativa escolhida tiver sido ocupada. Nenhum campo interno aparece nas respostas A2A.

Em `agente/src/agente/mcp_client.py`, a chamada usa `client.session.call_tool(..., allow_input_required=True)` para devolver a rodada crua à ponte. O handler de elicitation registrado serve para o SDK anunciar a capability; ele não responde perguntas nem consome automaticamente o ciclo MRTR.

## Decisões técnicas

- Dois processos ASGI independentes: o MCP usa o servidor de baixo nível e o transporte Streamable HTTP do SDK oficial; o agente usa o cliente do mesmo SDK via HTTP e expõe o binding A2A em Starlette. As versões estão travadas nos requirements e no `pyproject.toml`.
- `servidor-mcp/src/salas_mcp/state.py` protege o `requestState` com JSON canônico e HMAC-SHA256, incluindo o prefixo de versão na assinatura. O token contém o pedido, a chave da pergunta, as alternativas e uma expiração de 15 minutos. O servidor rejeita adulteração, expiração e argumentos divergentes; não mantém um contexto de pausa em memória. Após reinício com o mesmo segredo, o token continua utilizável e a disponibilidade é reavaliada.
- Tasks, argumentos originais, trace e pausas ficam em memória, isolados por `taskId`, na ponte. Reiniciar o agente perde as Tasks; reiniciar o MCP restaura as reservas fornecidas em `dados/`.
- As regras de sala pertencem exclusivamente a `servidor-mcp/src/salas_mcp/domain.py`. Datas precisam ter fuso; são normalizadas para São Paulo (`-03:00`), e todo o intervalo deve estar na janela de 08:00 a 20:00 do mesmo dia, com duração máxima de duas horas.
- O agente executa `tools/list` antes da primeira chamada, usa o schema descoberto para validar argumentos e lê a versão de `politica://uso` para o artifact. O SDK inclui metadados obrigatórios, capabilities e headers espelhados em cada request.
- No MCP SDK 2.3.0, `check_client_capability` verifica a presença de `elicitation`, mas não seus modos. Antes de emitir uma pergunta, o servidor confere explicitamente `ctx.session.client_capabilities.elicitation.form`, usando as capabilities do request corrente. Declarar apenas `url` ou uma elicitation sem modo recebe HTTP 400 com `-32021`.
- O endpoint A2A valida a estrutura dos parâmetros de `SendMessage` e `GetTask` com JSON Schema antes de acessar seus campos. Mensagens, partes de texto ou identificadores malformados recebem erro JSON-RPC `-32602`, preservando o id do request.
- O `traceparent` original fica associado à Task e é preservado nas retomadas. O MCP registra método, id e trace no stderr. Chamadas assíncronas permitem consultar `GetTask` enquanto uma Task está em `WORKING`; erros de transporte terminam em `FAILED`.

Para instalar e executar as verificações de desenvolvimento:

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/black --check servidor-mcp agente tests
.venv/bin/ruff check servidor-mcp agente tests
.venv/bin/mypy --config-file pyproject.toml agente/src/agente servidor-mcp/src/salas_mcp
.venv/bin/python -m unittest discover -s tests -v
```

Os 18 testes cobrem componentes e integração HTTP com processos reais: descoberta, schemas, erros, integridade e expiração do token, retomada após reinício, janela em São Paulo, isolamento de Tasks, novas pausas, propagação de trace, consulta durante `WORKING`, exigência de elicitation em form mode por request e rejeição de parâmetros A2A malformados. A infraestrutura de teste usa portas próprias, segredos temporários e encerra somente os processos que iniciou. O teste de suspensão de processo é específico de POSIX e é ignorado em outras plataformas.

`dados/`, `validador/` e `exemplos/` foram preservados. A instalação, os testes e as verificações Black, Ruff e mypy foram repetidos em uma cópia limpa com uma nova venv.

## Saída do validador

Execução em 2026-10-05, Python 3.12.3, ambiente limpo, portas locais isoladas, ambos os processos iniciados do zero e código de saída 0. O trace-id abaixo foi confirmado no stderr do MCP. A saída foi mantida literalmente:

```text
trace-id desta execucao: 650181de561e7b198b674c34d1e2fa8b
procure esse valor no stderr do servidor MCP para conferir a propagacao do traceparent.

PASS 01 tools/list traz as tres tools
PASS 02 toda tool tem inputSchema de objeto
PASS 03 listar_salas devolve structuredContent e o mesmo JSON em texto
PASS 04 _meta sem protocolVersion devolve -32602 e HTTP 400
PASS 05 _meta sem clientCapabilities devolve -32602 e HTTP 400
PASS 06 tool inexistente e recusada, por -32602 ou por isError
PASS 07 resources/read de politica://uso devolve a politica
PASS 08 resources/read de URI inexistente devolve -32602
PASS 09 sala inexistente devolve isError com a mensagem exata
PASS 10 fora da janela devolve isError com a mensagem exata
PASS 11 duracao acima de 2h devolve isError com a mensagem exata
PASS 12 intervalo invertido devolve isError com a mensagem exata
PASS 13 conflito devolve input_required com inputRequests e requestState
PASS 14 a elicitation e form mode e oferece as alternativas na ordem certa
PASS 15 conflito sem a capability elicitation devolve -32021 e HTTP 400
PASS 16 retry com inputResponses e requestState conclui a reserva
PASS 17 requestState adulterado e rejeitado com -32602
PASS 18 argumentos adulterados no retry nao tomam efeito
PASS 19 recusa conclui sem reservar e sem isError
PASS 20 conflito sem alternativa possivel devolve isError com a mensagem exata

PASS 21 agent card responde 200 no well-known com JSON
PASS 22 o card declara a interface JSON-RPC com url e versao 1.0
PASS 23 o card declara a skill reservar-sala
PASS 24 SendMessage com sala livre conclui a Task
PASS 25 o artifact chama reserva e traz a versao da politica
PASS 26 GetTask devolve id, contextId e estado corrente
PASS 27 SendMessage com sala ocupada pausa a Task
PASS 28 a Task pausada lista as alternativas na ordem certa
PASS 29 escolha fora do enum mantem a Task pausada
PASS 30 a continuacao conclui a Task na sala escolhida
PASS 31 SendMessage em Task terminal e recusado
PASS 32 a recusa termina a Task em CANCELED
PASS 33 duas Tasks pausadas ao mesmo tempo concluem cada uma com a sua reserva
PASS 34 nenhuma resposta A2A carrega o requestState
PASS 35 sala inexistente termina a Task em FAILED com a mensagem da tool
PASS 36 o agente e deterministico: o mesmo pedido produz a mesma pausa

resumo: 36 passaram, 0 falharam, de 36 verificacoes
```
