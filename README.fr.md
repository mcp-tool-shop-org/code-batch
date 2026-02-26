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

Moteur d'exécution par lots basé sur le contenu, avec découpage déterministe et résultats interrogeables.

**Qu'est-ce que c'est :** Un environnement d'exécution basé sur un système de fichiers qui sauvegarde le code, effectue le découpage de manière déterministe et indexe chaque résultat pour des requêtes structurées, sans nécessiter de base de données.

**À qui s'adresse-t-il :** Aux développeurs qui créent des pipelines d'analyse de code reproductibles, des intégrations CI ou des flux de travail de transformation par lots qui nécessitent une reproductibilité et une auditabilité.

**Pourquoi est-ce différent :** Chaque entrée est adressée par son contenu et chaque exécution est déterministe. Relancez le même lot six mois plus tard et obtenez des résultats identiques. Interrogez les résultats par type sémantique sans avoir à analyser les journaux.

## Aperçu

CodeBatch fournit un environnement d'exécution basé sur un système de fichiers pour effectuer des transformations déterministes sur des bases de code. Il capture les entrées sous forme de snapshots immuables, exécute les tâches dans des segments isolés et indexe tous les résultats sémantiques pour une interrogation efficace, sans nécessiter de base de données.

## Documentation

- **[SPEC.md](./SPEC.md)** — Spécification complète du stockage et de l'exécution.
- **[docs/TASKS.md](./docs/TASKS.md)** — Référence des tâches (analyse, analyse, symboles, lint).
- **[CHANGELOG.md](./CHANGELOG.md)** — Historique des versions.

## Démarrage rapide

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

## Flux de travail manuel (Phase 5)

La phase 5 ajoute des commandes conviviales qui combinent des fonctionnalités existantes :

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

## Découvrabilité

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

## Alias de requête

```bash
# Show errors
codebatch errors --batch <id> --store ./store

# List files in a snapshot
codebatch files --batch <id> --store ./store

# Top output kinds
codebatch top --batch <id> --store ./store
```

## Exploration et comparaison (Phase 6)

La phase 6 ajoute des vues en lecture seule pour explorer les résultats et comparer les lots, sans modifier le stockage.

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

## Commandes de bas niveau

Pour un contrôle plus précis, les commandes d'origine restent disponibles :

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

## Gestion des versions de la spécification

La spécification utilise la gestion des versions sémantiques avec des marqueurs "brouillon/stable". Chaque version est étiquetée dans Git (par exemple, `spec-v1.0-draft`). Les modifications majeures incrémentent la version principale. Les implémentations doivent déclarer quelle version de la spécification elles ciblent et tolérer les champs inconnus pour la compatibilité ascendante.

## Structure du projet

```
schemas/      JSON Schema definitions for all record types
src/          Core implementation
tests/        Test suites and fixtures
docs/         Documentation
.github/      CI/CD workflows
```

## Support

- **Questions / aide :** [Discussions](https://github.com/mcp-tool-shop-org/code-batch/discussions)
- **Signalement de bogues :** [Issues](https://github.com/mcp-tool-shop-org/code-batch/issues)

## Licence

MIT
