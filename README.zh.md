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

基于内容寻址的批量执行引擎，具有确定性的分片和可查询的输出。

**是什么：** 这是一个基于文件系统的执行平台，它会快照代码，以确定性的方式进行分片，并索引所有输出，以便进行结构化查询——无需数据库。

**适用于：** 正在构建可重复的代码分析流水线、CI 集成或需要可重复性和可审计性的批量转换工作流程的开发人员。

**与众不同之处：** 每一个输入都基于内容进行寻址，并且每一次执行都是确定性的。 即使在六个月后重新运行相同的批次，也能获得完全相同的结果。 可以通过语义类型查询输出，而无需解析日志。

## 概述

CodeBatch 提供了一个基于文件系统的执行平台，用于对代码库进行确定性的转换。 它将输入捕获为不可变的快照，在隔离的分片中执行任务，并索引所有语义输出，以便进行高效的查询——无需数据库。

## 文档

- **[SPEC.md](./SPEC.md)** — 完整的存储和执行规范
- **[docs/TASKS.md](./docs/TASKS.md)** — 任务参考（解析、分析、符号、代码检查）
- **[CHANGELOG.md](./CHANGELOG.md)** — 版本历史

## 快速开始

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

## 人工工作流程（第五阶段）

第五阶段添加了对用户友好的命令，这些命令将现有功能组合在一起：

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

## 可发现性

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

## 查询别名

```bash
# Show errors
codebatch errors --batch <id> --store ./store

# List files in a snapshot
codebatch files --batch <id> --store ./store

# Top output kinds
codebatch top --batch <id> --store ./store
```

## 探索与比较（第六阶段）

第六阶段添加了只读视图，用于探索输出并比较批次——而无需修改存储。

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

## 底层命令

为了实现精细的控制，原始命令仍然可用：

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

## 规范版本控制

该规范使用语义版本控制，并带有草案/稳定标记。 每个版本都标记在 Git 中（例如，`spec-v1.0-draft`）。 破坏性更改会增加主版本号。 实现应声明其目标规范版本，并容忍未知字段以实现向前兼容性。

## 项目结构

```
schemas/      JSON Schema definitions for all record types
src/          Core implementation
tests/        Test suites and fixtures
docs/         Documentation
.github/      CI/CD workflows
```

## 支持

- **问题/帮助：** [讨论](https://github.com/mcp-tool-shop-org/code-batch/discussions)
- **错误报告：** [问题](https://github.com/mcp-tool-shop-org/code-batch/issues)

## 许可证

MIT
