# Tests

## Fixture Corpus

The `fixtures/corpus/` directory contains test files designed to exercise edge cases in snapshot creation and file processing.

### Files in Corpus

| File | Purpose |
|------|---------|
| `hello.py` | Simple Python file with LF line endings |
| `crlf_example.txt` | Text file with CRLF line endings |
| `unicode_路径.txt` | UTF-8 filename with CJK characters |
| `emoji_🎉.md` | UTF-8 filename with emoji |
| `binary.bin` | Binary file (not text) |
| `empty.txt` | Empty file (0 bytes) |

### Windows-Only Fixtures

The `fixtures/corpus-windows-only/` directory contains files that test Windows-specific edge cases:

| File | Purpose |
|------|---------|
| `CaseA.cs` | Case collision pair (upper) - tests case-insensitive filesystem behavior |
| `casea.cs` | Case collision pair (lower) - expected conflict on Windows |

**Note:** These files cannot coexist on case-insensitive filesystems. On Windows, only one will exist. On case-sensitive systems (Linux/macOS with case-sensitive FS), both can exist.

### Golden Outputs

The `fixtures/golden/snapshot/` directory contains expected outputs:

- `snapshot.json` - Expected snapshot metadata
- `files.index.jsonl` - Expected file index records

### Ordering Rules

File index records are sorted by:
1. `path_key` (normalized lowercase path) ascending
2. Stable sort preserves insertion order for ties

This ensures deterministic output across platforms.

## Running Tests

```bash
# Run all tests
python -m pytest tests/

# Run with coverage
python -m pytest tests/ --cov=src
```
