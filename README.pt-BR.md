<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.zh.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.fr.md">Français</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.pt-BR.md">Português (BR)</a>
</p>

<p align="center">
  
            <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/brand/main/logos/code-batch/readme.png"
           alt="CodeBatch" width="400">
</p>

<p align="center">
  <a href="https://github.com/mcp-tool-shop-org/code-batch/actions/workflows/ci.yml"><img src="https://github.com/mcp-tool-shop-org/code-batch/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT License"></a>
  <a href="https://mcp-tool-shop-org.github.io/code-batch/"><img src="https://img.shields.io/badge/Landing_Page-live-blue" alt="Landing Page"></a>
</p>

Motor de execução em lote com endereçamento de conteúdo, particionamento determinístico e saídas pesquisáveis.

**O que é:** Uma plataforma de execução baseada em sistema de arquivos que captura o código, particiona o trabalho de forma determinística e indexa todas as saídas para consultas estruturadas – sem a necessidade de um banco de dados.

**Para quem é:** Desenvolvedores que criam pipelines de análise de código repetíveis, integrações de CI ou fluxos de trabalho de transformação em lote que exigem reprodutibilidade e auditabilidade.

**O que o diferencia:** Cada entrada é endereçada por conteúdo e cada execução é determinística. Execute o mesmo lote seis meses depois e obtenha resultados idênticos. Consulte as saídas por tipo semântico, sem analisar logs.

## Visão geral

O CodeBatch oferece uma plataforma de execução baseada em sistema de arquivos para realizar transformações determinísticas em bases de código. Ele captura as entradas como snapshots imutáveis, executa o trabalho em partições isoladas e indexa todas as saídas semânticas para consultas eficientes – sem a necessidade de um banco de dados.

## Documentação

- **[SPEC.md](./SPEC.md)** — Especificação completa de armazenamento e execução.
- **[docs/TASKS.md](./docs/TASKS.md)** — Referência de tarefas (análise, análise, símbolos, lint).
- **[CHANGELOG.md](./CHANGELOG.md)** — Histórico de versões.

## Início rápido

```bash
# Initialize a store
codebatch init ./store

# Create a snapshot of a directory
codebatch snapshot ./my-project --store ./store

# List available pipelines
codebatch pipelines

# Initialize a batch with a pipeline
codebatch batch init --snapshot <id> --pipeline full --store ./store

# Run all tasks and shards (Phase 5 workflow)
codebatch run --batch <id> --store ./store

# View progress
codebatch status --batch <id> --store ./store

# View summary
codebatch summary --batch <id> --store ./store
```

## Fluxo de trabalho humano (Fase 5)

A Fase 5 adiciona comandos amigáveis ao usuário que combinam primitivas existentes:

```bash
# Run entire batch (no manual shard iteration needed)
codebatch run --batch <id> --store ./store

# Resume interrupted execution
codebatch resume --batch <id> --store ./store

# Progress summary
codebatch status --batch <id> --store ./store

# Output summary
codebatch summary --batch <id> --store ./store
```

## Descoberta

```bash
# List pipelines
codebatch pipelines

# Show pipeline details
codebatch pipeline full

# List tasks in a batch
codebatch tasks --batch <id> --store ./store

# List shards for a task
codebatch shards --batch <id> --task 01_parse --store ./store
```

## Apelidos de consulta

```bash
# Show errors
codebatch errors --batch <id> --store ./store

# List files in a snapshot
codebatch files --batch <id> --store ./store

# Top output kinds
codebatch top --batch <id> --store ./store
```

## Exploração e comparação (Fase 6)

A Fase 6 adiciona visualizações somente leitura para explorar as saídas e comparar lotes – sem modificar o armazenamento.

```bash
# Inspect all outputs for a file
codebatch inspect src/main.py --batch <id> --store ./store

# Compare two batches
codebatch diff <batchA> <batchB> --store ./store

# Show regressions (new/worsened diagnostics)
codebatch regressions <batchA> <batchB> --store ./store

# Show improvements (fixed/improved diagnostics)
codebatch improvements <batchA> <batchB> --store ./store

# Explain data sources for any command
codebatch inspect src/main.py --batch <id> --store ./store --explain
```

## Comandos de baixo nível

Para um controle mais detalhado, os comandos originais permanecem disponíveis:

```bash
# Run a specific shard
codebatch run-shard --batch <id> --task 01_parse --shard ab --store ./store

# Query outputs
codebatch query outputs --batch <id> --task 01_parse --store ./store

# Query diagnostics
codebatch query diagnostics --batch <id> --task 01_parse --store ./store

# Build LMDB acceleration cache
codebatch index-build --batch <id> --store ./store
```

## Versionamento da especificação

A especificação utiliza versionamento semântico com marcadores de rascunho/estável. Cada versão é marcada no git (por exemplo, `spec-v1.0-draft`). Alterações que quebram a compatibilidade incrementam a versão principal. As implementações devem declarar qual versão da especificação elas utilizam e tolerar campos desconhecidos para compatibilidade com versões futuras.

## Estrutura do projeto

```
schemas/      JSON Schema definitions for all record types
src/          Core implementation
tests/        Test suites and fixtures
docs/         Documentation
.github/      CI/CD workflows
```

## Suporte

- **Dúvidas / ajuda:** [Discussões](https://github.com/mcp-tool-shop-org/code-batch/discussions)
- **Relatórios de bugs:** [Problemas](https://github.com/mcp-tool-shop-org/code-batch/issues)

## Licença

MIT
