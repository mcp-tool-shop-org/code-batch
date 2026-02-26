<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.zh.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.fr.md">Français</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.pt-BR.md">Português (BR)</a>
</p>

<p align="center">
  <img src="assets/logo.png" alt="CodeBatch" width="400">
</p>

<p align="center">
  <a href="https://github.com/mcp-tool-shop-org/code-batch/actions/workflows/ci.yml"><img src="https://github.com/mcp-tool-shop-org/code-batch/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT License"></a>
  <a href="https://mcp-tool-shop-org.github.io/code-batch/"><img src="https://img.shields.io/badge/Landing_Page-live-blue" alt="Landing Page"></a>
</p>

Motore di esecuzione batch orientato ai contenuti, con sharding deterministico e output interrogabili.

**Cos'è:** Un ambiente di esecuzione basato su filesystem che salva il codice, suddivide il lavoro in modo deterministico e indicizza tutti gli output per interrogazioni strutturate, senza la necessità di un database.

**A chi è rivolto:** Sviluppatori che creano pipeline di analisi del codice ripetibili, integrazioni CI o flussi di lavoro di trasformazione batch che richiedono riproducibilità e auditabilità.

**Cosa lo rende diverso:** Ogni input è identificato dal suo contenuto e ogni esecuzione è deterministica. Riavviare la stessa elaborazione a distanza di sei mesi produrrà risultati identici. È possibile interrogare gli output in base al tipo semantico senza dover analizzare i log.

## Panoramica

CodeBatch fornisce un ambiente di esecuzione basato su filesystem per eseguire trasformazioni deterministiche su basi di codice. Cattura gli input come snapshot immutabili, esegue il lavoro in shard isolati e indicizza tutti gli output semantici per interrogazioni efficienti, senza richiedere un database.

## Documentazione

- **[SPEC.md](./SPEC.md)** — Specifiche complete di archiviazione ed esecuzione
- **[docs/TASKS.md](./docs/TASKS.md)** — Riferimento alle attività (analisi, controllo, simboli, linting)
- **[CHANGELOG.md](./CHANGELOG.md)** — Cronologia delle versioni

## Guida Rapida

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

## Flusso di lavoro manuale (Fase 5)

La Fase 5 aggiunge comandi intuitivi che combinano funzionalità esistenti:

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

## Scoperta

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

## Alias di interrogazione

```bash
# Show errors
codebatch errors --batch <id> --store ./store

# List files in a snapshot
codebatch files --batch <id> --store ./store

# Top output kinds
codebatch top --batch <id> --store ./store
```

## Esplorazione e confronto (Fase 6)

La Fase 6 aggiunge viste di sola lettura per esplorare gli output e confrontare le elaborazioni, senza modificare l'archivio.

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

## Comandi di basso livello

Per un controllo più preciso, i comandi originali rimangono disponibili:

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

## Versionamento delle specifiche

Le specifiche utilizzano il versionamento semantico con indicatori "bozza/stabile". Ogni versione è contrassegnata in git (ad esempio, `spec-v1.0-draft`). Le modifiche incompatibili incrementano la versione principale. Le implementazioni devono dichiarare quale versione delle specifiche utilizzano e tollerare i campi sconosciuti per la compatibilità con le versioni future.

## Struttura del progetto

```
schemas/      JSON Schema definitions for all record types
src/          Core implementation
tests/        Test suites and fixtures
docs/         Documentation
.github/      CI/CD workflows
```

## Supporto

- **Domande / aiuto:** [Discussioni](https://github.com/mcp-tool-shop-org/code-batch/discussions)
- **Segnalazione di bug:** [Problemi](https://github.com/mcp-tool-shop-org/code-batch/issues)

## Licenza

MIT
