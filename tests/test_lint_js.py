"""Tests for JS/TS AST-aware lint rules (L101-L103).

Uses synthetic tree-sitter AST structures to test the lint rules
without requiring tree-sitter to be installed.
"""

import pytest

from codebatch.tasks.lint import (
    lint_js_unused_imports,
    lint_js_unused_variables,
    lint_js_variable_shadowing,
    lint_js_ast,
    _js_collect_import_names,
    _js_collect_used_names,
    _js_collect_declared_variables,
)


def _make_identifier(name: str, row: int = 0, col: int = 0) -> dict:
    """Helper: create a tree-sitter identifier node."""
    return {
        "type": "identifier",
        "name": name,
        "start_point": {"row": row, "column": col},
        "end_point": {"row": row, "column": col + len(name)},
    }


def _make_import(names: list[str], source: str, row: int = 0) -> dict:
    """Helper: create a tree-sitter import_statement with named imports.

    Simulates: import { name1, name2 } from 'source'
    """
    specifiers = []
    for name in names:
        specifiers.append({
            "type": "import_specifier",
            "start_point": {"row": row, "column": 0},
            "end_point": {"row": row, "column": 10},
            "children": [_make_identifier(name, row)],
        })

    return {
        "type": "import_statement",
        "start_point": {"row": row, "column": 0},
        "end_point": {"row": row, "column": 50},
        "children": [
            {
                "type": "import_clause",
                "start_point": {"row": row, "column": 0},
                "end_point": {"row": row, "column": 30},
                "children": [
                    {
                        "type": "named_imports",
                        "start_point": {"row": row, "column": 0},
                        "end_point": {"row": row, "column": 30},
                        "children": specifiers,
                    }
                ],
            },
            {
                "type": "string",
                "name": None,
                "value": f"'{source}'",
                "start_point": {"row": row, "column": 35},
                "end_point": {"row": row, "column": 50},
            },
        ],
    }


def _make_default_import(name: str, source: str, row: int = 0) -> dict:
    """Helper: create import Foo from 'source'."""
    return {
        "type": "import_statement",
        "start_point": {"row": row, "column": 0},
        "end_point": {"row": row, "column": 40},
        "children": [
            {
                "type": "import_clause",
                "start_point": {"row": row, "column": 7},
                "end_point": {"row": row, "column": 10},
                "children": [_make_identifier(name, row)],
            },
            {
                "type": "string",
                "value": f"'{source}'",
                "start_point": {"row": row, "column": 20},
                "end_point": {"row": row, "column": 40},
            },
        ],
    }


def _make_var_decl(name: str, value_children: list[dict] | None = None, row: int = 1) -> dict:
    """Helper: create const name = ..."""
    declarator = {
        "type": "variable_declarator",
        "name": name,
        "start_point": {"row": row, "column": 6},
        "end_point": {"row": row, "column": 20},
        "children": [
            _make_identifier(name, row),
        ],
    }
    if value_children:
        declarator["children"].extend(value_children)

    return {
        "type": "lexical_declaration",
        "start_point": {"row": row, "column": 0},
        "end_point": {"row": row, "column": 20},
        "children": [declarator],
    }


def _make_function_decl(name: str, params: list[str], body_children: list[dict], row: int = 2) -> dict:
    """Helper: create function name(params) { body }."""
    param_nodes = []
    for p in params:
        param_nodes.append(_make_identifier(p, row))

    return {
        "type": "function_declaration",
        "name": name,
        "start_point": {"row": row, "column": 0},
        "end_point": {"row": row + 3, "column": 1},
        "children": [
            _make_identifier(name, row),
            {
                "type": "formal_parameters",
                "start_point": {"row": row, "column": len(name) + 9},
                "end_point": {"row": row, "column": len(name) + 15},
                "children": param_nodes,
            },
            {
                "type": "statement_block",
                "start_point": {"row": row, "column": 20},
                "end_point": {"row": row + 3, "column": 1},
                "children": body_children,
            },
        ],
    }


def _make_call(func_name: str, args: list[str], row: int = 3) -> dict:
    """Helper: create funcName(arg1, arg2)."""
    return {
        "type": "expression_statement",
        "start_point": {"row": row, "column": 0},
        "end_point": {"row": row, "column": 20},
        "children": [
            {
                "type": "call_expression",
                "start_point": {"row": row, "column": 0},
                "end_point": {"row": row, "column": 20},
                "children": [
                    _make_identifier(func_name, row),
                    {
                        "type": "arguments",
                        "start_point": {"row": row, "column": len(func_name)},
                        "end_point": {"row": row, "column": 20},
                        "children": [_make_identifier(a, row) for a in args],
                    },
                ],
            }
        ],
    }


def _make_program(children: list[dict]) -> dict:
    """Helper: wrap children in a tree-sitter program root."""
    return {
        "type": "program",
        "ast_mode": "full",
        "parser": "tree-sitter",
        "start_point": {"row": 0, "column": 0},
        "end_point": {"row": 100, "column": 0},
        "children": children,
    }


class TestJsCollectImportNames:
    """Tests for _js_collect_import_names."""

    def test_collects_named_imports(self):
        ast = _make_program([
            _make_import(["foo", "bar"], "module"),
        ])
        imports = _js_collect_import_names(ast)
        assert "foo" in imports
        assert "bar" in imports

    def test_collects_default_import(self):
        ast = _make_program([
            _make_default_import("React", "react"),
        ])
        imports = _js_collect_import_names(ast)
        assert "React" in imports

    def test_empty_program(self):
        ast = _make_program([])
        imports = _js_collect_import_names(ast)
        assert len(imports) == 0


class TestJsCollectUsedNames:
    """Tests for _js_collect_used_names."""

    def test_collects_identifiers_in_expressions(self):
        ast = _make_program([
            _make_call("console", ["data"]),
        ])
        used = _js_collect_used_names(ast)
        assert "console" in used
        assert "data" in used

    def test_skips_import_names(self):
        ast = _make_program([
            _make_import(["foo"], "module"),
        ])
        used = _js_collect_used_names(ast)
        assert "foo" not in used

    def test_skips_declaration_names(self):
        ast = _make_program([
            _make_var_decl("count"),
        ])
        used = _js_collect_used_names(ast)
        assert "count" not in used


class TestJsUnusedImports:
    """Tests for L101: unused imports in JS/TS."""

    def test_detects_unused_import(self):
        ast = _make_program([
            _make_import(["unused", "used"], "module"),
            _make_call("used", []),
        ])
        diags = lint_js_unused_imports(ast, "test.js")
        codes = [d["code"] for d in diags]
        names = [d["message"] for d in diags]
        assert "L101" in codes
        assert any("unused" in m for m in names)
        assert not any("used" in m and "unused" not in m for m in names)

    def test_no_false_positive_for_used_import(self):
        ast = _make_program([
            _make_import(["foo"], "module"),
            _make_call("foo", []),
        ])
        diags = lint_js_unused_imports(ast, "test.js")
        assert len(diags) == 0

    def test_no_imports_no_diagnostics(self):
        ast = _make_program([
            _make_call("console", ["hello"]),
        ])
        diags = lint_js_unused_imports(ast, "test.js")
        assert len(diags) == 0

    def test_all_imports_unused(self):
        ast = _make_program([
            _make_import(["alpha", "beta"], "module"),
        ])
        diags = lint_js_unused_imports(ast, "test.js")
        assert len(diags) == 2
        names = {d["message"].split("'")[1] for d in diags}
        assert names == {"alpha", "beta"}

    def test_default_import_used(self):
        ast = _make_program([
            _make_default_import("React", "react"),
            _make_call("React", []),
        ])
        diags = lint_js_unused_imports(ast, "test.tsx")
        assert len(diags) == 0


class TestJsUnusedVariables:
    """Tests for L102: unused variables in JS/TS."""

    def test_detects_unused_variable(self):
        ast = _make_program([
            _make_var_decl("unused", row=1),
            _make_call("console", ["other"], row=2),
        ])
        diags = lint_js_unused_variables(ast, "test.js")
        assert len(diags) == 1
        assert diags[0]["code"] == "L102"
        assert "unused" in diags[0]["message"]

    def test_used_variable_no_diagnostic(self):
        ast = _make_program([
            _make_var_decl("data", row=1),
            _make_call("process", ["data"], row=2),
        ])
        diags = lint_js_unused_variables(ast, "test.js")
        assert len(diags) == 0

    def test_skips_underscore_prefix(self):
        ast = _make_program([
            _make_var_decl("_unused", row=1),
        ])
        diags = lint_js_unused_variables(ast, "test.js")
        assert len(diags) == 0

    def test_skips_functions(self):
        ast = _make_program([
            _make_function_decl("myFunc", [], []),
        ])
        diags = lint_js_unused_variables(ast, "test.js")
        assert len(diags) == 0


class TestJsVariableShadowing:
    """Tests for L103: variable shadowing in JS/TS."""

    def test_detects_parameter_shadowing(self):
        """Function param that shadows a top-level variable."""
        ast = _make_program([
            _make_var_decl("data", row=0),
            _make_function_decl("process", ["data"], [
                _make_call("console", ["data"], row=4),
            ], row=2),
        ])
        diags = lint_js_variable_shadowing(ast, "test.js")
        assert len(diags) >= 1
        assert any(d["code"] == "L103" for d in diags)
        assert any("data" in d["message"] for d in diags)

    def test_no_shadowing_different_names(self):
        """No shadowing when names don't overlap."""
        ast = _make_program([
            _make_var_decl("x", row=0),
            _make_function_decl("fn", ["y"], [
                _make_call("console", ["y"], row=4),
            ], row=2),
        ])
        diags = lint_js_variable_shadowing(ast, "test.js")
        # No L103 for 'y' since 'y' doesn't shadow 'x'
        assert not any(d["code"] == "L103" for d in diags)


class TestJsLintAstIntegration:
    """Integration tests for lint_js_ast."""

    def test_runs_all_rules(self):
        """lint_js_ast runs L101 + L102 + L103."""
        ast = _make_program([
            _make_import(["unused_import"], "module", row=0),
            _make_var_decl("unused_var", row=1),
            _make_var_decl("outer", row=2),
            _make_function_decl("fn", ["outer"], [
                _make_call("console", ["outer"], row=6),
            ], row=4),
        ])
        diags = lint_js_ast(ast, "test.js", {})
        codes = {d["code"] for d in diags}
        assert "L101" in codes, "Should detect unused import"
        assert "L102" in codes, "Should detect unused variable"
        assert "L103" in codes, "Should detect shadowing"

    def test_config_disables_rules(self):
        """Config flags can disable individual rules."""
        ast = _make_program([
            _make_import(["unused"], "module"),
        ])
        diags = lint_js_ast(ast, "test.js", {"check_unused_imports": False})
        assert len(diags) == 0

    def test_all_fields_present(self):
        """Diagnostic records have all required fields."""
        ast = _make_program([
            _make_import(["unused"], "module"),
        ])
        diags = lint_js_ast(ast, "test.js", {})
        for d in diags:
            assert "kind" in d
            assert d["kind"] == "diagnostic"
            assert "path" in d
            assert "severity" in d
            assert "code" in d
            assert "message" in d
            assert "line" in d
            assert "col" in d
