## ADDED Requirements

### Requirement: Organização por responsabilidade
O código SHALL separar transporte, domínio, codec de `requestState`, cliente MCP e ponte A2A em módulos identificáveis, sem duplicar regras de negócio entre processos.

#### Scenario: Regra de sala permanece no MCP
- **WHEN** o agente processa uma reserva ou retry
- **THEN** ele apenas traduz envelopes e estados, delegando conflitos, política e alternativas ao MCP.

### Requirement: Tipagem e erros explícitos
Os módulos principais MUST declarar tipos para entradas e saídas públicas e MUST usar exceções específicas para validação, protocolo e estado inválido.

#### Scenario: Erro de estado adulterado
- **WHEN** um `requestState` inválido chega ao servidor
- **THEN** uma exceção específica é convertida em erro JSON-RPC `-32602`, sem traceback na resposta HTTP.

### Requirement: Qualidade automatizada
O projeto MUST fornecer configuração reproduzível para formatação, lint, testes e checagem de tipos, e os testes MUST executar sem alterar `dados/`, `validador/` ou `exemplos/`.

#### Scenario: Verificação local
- **WHEN** o desenvolvedor executa o comando de qualidade documentado
- **THEN** Black/Ruff, checagem de tipos e testes são executados com configuração versionada.

### Requirement: Logs seguros e úteis
O sistema MUST registrar método, id e trace context no stderr quando aplicável, mas MUST NOT registrar ou devolver `requestState` em respostas A2A.

#### Scenario: Diagnóstico de retry
- **WHEN** um retry MCP é recebido
- **THEN** o log contém método, id e traceparent, sem conter o token completo de `requestState`.

### Requirement: Dependências coerentes
As dependências declaradas MUST corresponder ao runtime e MUST separar dependências de desenvolvimento das dependências necessárias para executar MCP e A2A.

#### Scenario: Instalação limpa
- **WHEN** um clone novo instala as dependências documentadas em um venv
- **THEN** os dois processos e os testes iniciam sem instalação manual adicional.
