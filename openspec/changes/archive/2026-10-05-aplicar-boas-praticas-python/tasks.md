## 1. Estrutura e modelos

- [x] 1.1 Separar transporte, domínio, codec de `requestState`, cliente MCP e ponte A2A em módulos coesos
- [x] 1.2 Criar dataclasses e type hints para reservas, Tasks, respostas MCP e contextos internos
- [x] 1.3 Centralizar constantes, mensagens de erro e configurações de portas/URLs

## 2. Robustez e segurança

- [x] 2.1 Criar exceções específicas para validação, protocolo e `requestState`, mapeando-as nos adaptadores HTTP
- [x] 2.2 Garantir que logs e serialização A2A nunca exponham o `requestState`
- [x] 2.3 Cobrir adulteração, expiração, retry após restart e isolamento de estado com testes automatizados

## 3. Tooling e dependências

- [x] 3.1 Adicionar `pyproject.toml` com configurações de Black, Ruff, Pytest e mypy
- [x] 3.2 Separar dependências de runtime e desenvolvimento e remover declarações não utilizadas
- [x] 3.3 Documentar um comando único de qualidade e instalação em ambiente limpo

## 4. Testes e validação

- [x] 4.1 Expandir testes unitários para domínio, codec, parser e máquina de estados
- [x] 4.2 Executar Black, Ruff, checagem de tipos e testes sem alterar diretórios protegidos
- [x] 4.3 Executar o validador MCP/A2A completo e confirmar 36/36 após a refatoração
- [x] 4.4 Atualizar o README com as decisões de manutenção e a saída da validação final
