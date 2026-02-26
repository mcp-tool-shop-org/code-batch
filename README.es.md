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

Motor de ejecución por lotes con direccionamiento de contenido, fragmentación determinista y resultados consultables.

**¿Qué es?:** Un entorno de ejecución basado en un sistema de archivos que captura el código, fragmenta el trabajo de forma determinista e indexa todas las salidas para consultas estructuradas, sin necesidad de una base de datos.

**Para quién es:** Desarrolladores que crean pipelines de análisis de código repetibles, integraciones de CI o flujos de trabajo de transformación por lotes que requieren reproducibilidad y trazabilidad.

**¿Por qué es diferente?:** Cada entrada se identifica por su contenido y cada ejecución es determinista. Ejecute el mismo lote seis meses después y obtenga resultados idénticos. Consulte las salidas por tipo semántico sin necesidad de analizar registros.

## Descripción general

CodeBatch proporciona un entorno de ejecución basado en un sistema de archivos para realizar transformaciones deterministas sobre bases de código. Captura las entradas como instantáneas inmutables, ejecuta el trabajo en fragmentos aislados e indexa todas las salidas semánticas para una consulta eficiente, sin necesidad de una base de datos.

## Documentación

- **[SPEC.md](./SPEC.md)** — Especificación completa de almacenamiento y ejecución.
- **[docs/TASKS.md](./docs/TASKS.md)** — Referencia de tareas (parse, analyze, symbols, lint).
- **[CHANGELOG.md](./CHANGELOG.md)** — Historial de versiones.

## Inicio rápido

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

## Flujo de trabajo humano (Fase 5)

La Fase 5 agrega comandos fáciles de usar que combinan funciones básicas existentes:

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

## Descubrimiento

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

## Alias de consulta

```bash
# Show errors
codebatch errors --batch <id> --store ./store

# List files in a snapshot
codebatch files --batch <id> --store ./store

# Top output kinds
codebatch top --batch <id> --store ./store
```

## Exploración y comparación (Fase 6)

La Fase 6 agrega vistas de solo lectura para explorar las salidas y comparar los lotes, sin modificar el almacenamiento.

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

## Comandos de bajo nivel

Para un control más preciso, los comandos originales siguen estando disponibles:

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

## Versionado de la especificación

La especificación utiliza el versionado semántico con marcadores de "borrador" y "estable". Cada versión está etiquetada en git (por ejemplo, `spec-v1.0-draft`). Los cambios importantes incrementan la versión principal. Las implementaciones deben declarar qué versión de la especificación utilizan y tolerar campos desconocidos para la compatibilidad hacia adelante.

## Estructura del proyecto

```
schemas/      JSON Schema definitions for all record types
src/          Core implementation
tests/        Test suites and fixtures
docs/         Documentation
.github/      CI/CD workflows
```

## Soporte

- **Preguntas / ayuda:** [Discusiones](https://github.com/mcp-tool-shop-org/code-batch/discussions)
- **Informes de errores:** [Problemas](https://github.com/mcp-tool-shop-org/code-batch/issues)

## Licencia

MIT
