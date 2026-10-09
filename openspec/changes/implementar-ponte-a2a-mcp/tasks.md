## 1. Preparação do projeto

- [x] 1.1 Criar os pacotes Python independentes em `servidor-mcp/` e `agente/`, com pontos de entrada executáveis em Python 3.10+
- [x] 1.2 Declarar e travar as versões do SDK oficial MCP e das dependências HTTP/ASGI, sem dependências de LLM
- [x] 1.3 Adicionar testes automatizados sem modificar `dados/`, `validador/` ou `exemplos/`

## 2. Servidor MCP e transporte

- [x] 2.1 Expor Streamable HTTP em `/mcp` na porta 7301 e declarar capabilities de tools e resources
- [x] 2.2 Implementar validação stateless dos campos obrigatórios de `_meta` com erro `-32602` e HTTP 400
- [x] 2.3 Validar coerência de `MCP-Protocol-Version`, `Mcp-Method` e `Mcp-Name` com o corpo, retornando `-32020` em divergências
- [x] 2.4 Registrar método, id e `traceparent` de cada request no stderr
- [x] 2.5 Publicar `politica://uso` como `text/markdown` e rejeitar URIs desconhecidas com `-32602`

## 3. Domínio e tools MCP

- [x] 3.1 Carregar salas, reservas iniciais e versão da política dos arquivos fornecidos, mantendo novas reservas em memória
- [x] 3.2 Implementar validações compartilhadas de sala, intervalo, janela de uso e duração com as mensagens exatas do contrato
- [x] 3.3 Implementar `listar_salas` com schemas de entrada/saída, `structuredContent` e bloco de texto JSON equivalente
- [x] 3.4 Implementar `consultar_disponibilidade` com conflitos e resultados estruturados
- [x] 3.5 Implementar o caminho livre de `reservar_sala`, ids de reserva e visibilidade em consultas posteriores
- [x] 3.6 Testar as três tools, o resource, os erros de execução e os erros de protocolo isoladamente

## 4. MRTR e requestState

- [x] 4.1 Calcular no máximo três alternativas livres por capacidade e id e devolver elicitation form em um único `inputRequests`
- [x] 4.2 Rejeitar pausa sem capability `elicitation.form` com `-32021`, HTTP 400 e `requiredCapabilities`
- [x] 4.3 Implementar codec de `requestState` autocontido com JSON canônico, expiração de 15 minutos e HMAC-SHA256
- [x] 4.4 Validar `REQUEST_STATE_SECRET` hexadecimal com ao menos 32 bytes e falhar na inicialização quando ausente ou fraco
- [x] 4.5 Implementar retry usando os argumentos selados e rejeitar estado adulterado, expirado, de tool/chave incorreta ou escolha não oferecida com `-32602`
- [x] 4.6 Implementar `accept`, `decline` e `cancel`, incluindo o erro exato quando não houver alternativas
- [x] 4.7 Testar adulteração, argumentos divergentes, recusa e retry válido após restart do servidor com o mesmo segredo

## 5. Agente como host MCP

- [x] 5.1 Implementar cliente MCP HTTP com ids novos, `_meta` obrigatório e headers espelhados em todos os requests
- [x] 5.2 Executar `tools/list` antes do primeiro `tools/call` e descobrir `reservar_sala` em runtime
- [x] 5.3 Ler `politica://uso` e extrair a versão da primeira linha para uso no artifact
- [x] 5.4 Propagar o trace-id A2A em `_meta.traceparent` sem instalar callback que consuma a elicitation
- [x] 5.5 Testar descoberta, ordem das chamadas, metadados, headers e geração de ids distintos

## 6. Agente como servidor A2A

- [x] 6.1 Publicar Agent Card v1.0 em `/.well-known/agent-card.json` com `supportedInterfaces` JSON-RPC e skill `reservar-sala`
- [x] 6.2 Implementar parser determinístico do pedido fixo de reserva e rejeição de entradas inválidas sem LLM
- [x] 6.3 Implementar repositório de Tasks em memória e transições `SUBMITTED`, `WORKING`, `COMPLETED`, `FAILED`, `INPUT_REQUIRED` e `CANCELED`
- [x] 6.4 Implementar `SendMessage` para novas Tasks e `GetTask` com id, contextId, status, mensagens e artifacts
- [x] 6.5 Produzir artifact `reserva` no sucesso, propagar mensagem MCP na falha e rejeitar continuações de Tasks terminais
- [x] 6.6 Testar Agent Card, ciclo de vida, consulta, determinismo e imutabilidade terminal

## 7. Ponte MCP/A2A

- [x] 7.1 Implementar em `agente/src/agente/bridge.py` a tradução de `input_required` para `TASK_STATE_INPUT_REQUIRED` com a linha exata de alternativas
- [x] 7.2 Guardar chave, alternativas e `requestState` opaco em contexto interno isolado por `taskId`, excluído da serialização A2A
- [x] 7.3 Manter a Task pausada e repetir alternativas quando `escolha` estiver fora do enum, sem chamar o MCP
- [x] 7.4 Montar o retry aceito ou recusado com novo id, mesma chave, `inputResponses`, argumentos originais e `requestState` inalterado
- [x] 7.5 Mapear retry aceito para `COMPLETED` com artifact e recusa para `CANCELED`
- [x] 7.6 Testar duas Tasks simultaneamente pausadas, ausência de vazamento de `requestState` e trace propagation durante início e retomada

## 8. Documentação e validação final

- [x] 8.1 Substituir o README com comandos reproduzíveis de venv, segredo, subida dos dois processos e execução do validador
- [x] 8.2 Documentar os pontos de código da ponte, HMAC-SHA256, validade de 15 minutos e armazenamento em memória das Tasks
- [x] 8.3 Iniciar ambos os processos do zero e executar `python3 validador/validar.py --agente http://localhost:7300 --mcp http://localhost:7301` até obter 36 PASS e código zero
- [x] 8.4 Verificar manualmente retry após restart do MCP, trace-id no stderr, ids distintos no retry e ausência de alterações nos diretórios protegidos
- [x] 8.5 Colar no README a saída completa da última execução aprovada do validador
- [x] 8.6 Repetir a instalação e os comandos documentados a partir de um clone ou ambiente limpo

## 9. Correções identificadas na auditoria

- [x] 9.1 Usar efetivamente o SDK MCP v2 no servidor e no cliente, declarar capabilities e schemas completos, corrigir pontos de entrada e empacotamento
- [x] 9.2 Validar a janela completa em São Paulo e rejeitar adulteração de qualquer componente do requestState
- [x] 9.3 Tratar input_required em todas as rodadas, preservar trace por Task e disponibilizar GetTask durante WORKING
- [x] 9.4 Adicionar regressão automatizada para reinício, expiração, descoberta, janela, retomadas e consulta concorrente
- [x] 9.5 Reexecutar instalação limpa, qualidade e validador e publicar documentação com a saída integral
