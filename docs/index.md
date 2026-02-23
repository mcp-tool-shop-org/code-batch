# CodeBatch

Content-addressed batch execution engine with deterministic sharding and queryable outputs.

## What It Does

CodeBatch is a filesystem-based execution substrate that snapshots code, shards work deterministically, and indexes every output for structured queries. No database required.

## Key Features

- **Content-addressed storage** -- every input is hashed and immutable
- **Deterministic sharding** -- identical inputs always produce identical shard assignments
- **Queryable outputs** -- semantic indexes over execution results without parsing logs
- **Reproducibility** -- re-run the same batch months later with identical results
- **Gate system** -- configurable quality gates for release validation
- **Batch comparison** -- diff, regression, and improvement detection across runs

## Install

```bash
pip install codebatch
```

Or install with all optional dependencies:

```bash
pip install codebatch[all]
```

## Quick Start

```bash
codebatch init ./store
codebatch snapshot ./my-project --store ./store
codebatch batch init --snapshot <id> --pipeline full --store ./store
codebatch run --batch <id> --store ./store
codebatch summary --batch <id> --store ./store
```

## Links

- [Source Code](https://github.com/mcp-tool-shop-org/code-batch)
- [Full Specification](https://github.com/mcp-tool-shop-org/code-batch/blob/main/SPEC.md)
- [Task Reference](./TASKS.md)
- [Issues](https://github.com/mcp-tool-shop-org/code-batch/issues)
- [Discussions](https://github.com/mcp-tool-shop-org/code-batch/discussions)

## License

MIT
