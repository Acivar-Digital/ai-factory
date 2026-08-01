"""Unit tests for ast_analyzer, virtual_ast_buffer, and ast_verifier modules."""
from __future__ import annotations

import ast
import pytest

from factory.infra.ast_analyzer import (
    ComplexityVisitor,
    FunctionCandidateScanner,
    scan_file_for_anti_patterns,
)
from factory.infra.ast_verifier import (
    ComplexityVisitor as VerifierComplexityVisitor,
    SymbolScopeVisitor,
    _AttributeVisitor,
    _CallVisitor,
    _FunctionCandidateScanner,
    _extract_function_signature,
    ensure_pydantic_imports,
    extract_header_symbol_contract,
    run_lint_regression,
    verify_refactored_ast,
)
from factory.infra.virtual_ast_buffer import VirtualASTBuffer, ensure_pydantic_imports as vap_ensure_pydantic_imports


# ── ast_analyzer tests ──────────────────────────────────────────────────────

class TestScanFileForAntiPatternsClean:
    def test_clean_code_returns_empty_list(self):
        source = "def hello():\n    return 'world'\n"
        result = scan_file_for_anti_patterns(source, "test.py")
        assert result == []

    def test_clean_async_function_returns_empty_list(self):
        source = "async def hello():\n    return 'world'\n"
        result = scan_file_for_anti_patterns(source, "test.py")
        assert result == []


class TestScanFileForAntiPatternsTryPyramid:
    def test_detects_try_pyramid_priority_1(self):
        source = (
            "def foo():\n"
            "    try:\n"
            "        try:\n"
            "            pass\n"
            "        except Exception:\n"
            "            pass\n"
            "    except Exception:\n"
            "        pass\n"
        )
        result = scan_file_for_anti_patterns(source, "test.py")
        assert len(result) == 1
        assert result[0]["priority"] == 1
        assert result[0]["function_name"] == "foo"


class TestScanFileForAntiPatternsDeepNesting:
    def test_detects_deep_nesting_priority_2(self):
        source = (
            "def foo():\n"
            "    if True:\n"
            "        if True:\n"
            "            if True:\n"
            "                if True:\n"
            "                    pass\n"
        )
        result = scan_file_for_anti_patterns(source, "test.py")
        assert len(result) == 1
        assert result[0]["priority"] == 2
        assert result[0]["function_name"] == "foo"


class TestScanFileForAntiPatternsCC:
    def test_detects_cc_exceeds_5_priority_3(self):
        source = (
            "def foo(x):\n"
            "    if x > 1:\n"
            "        pass\n"
            "    if x > 2:\n"
            "        pass\n"
            "    if x > 3:\n"
            "        pass\n"
            "    if x > 4:\n"
            "        pass\n"
            "    if x > 5:\n"
            "        pass\n"
            "    if x > 6:\n"
            "        pass\n"
        )
        result = scan_file_for_anti_patterns(source, "test.py")
        assert len(result) == 1
        assert result[0]["priority"] == 3
        assert result[0]["function_name"] == "foo"


class TestScanFileForAntiPatternsSorting:
    def test_results_sorted_by_priority(self):
        source = (
            "def foo():\n"
            "    try:\n"
            "        try:\n"
            "            pass\n"
            "        except Exception:\n"
            "            pass\n"
            "    except Exception:\n"
            "        pass\n"
            "\n"
            "def bar(x):\n"
            "    if x > 1:\n"
            "        pass\n"
            "    if x > 2:\n"
            "        pass\n"
            "    if x > 3:\n"
            "        pass\n"
            "    if x > 4:\n"
            "        pass\n"
            "    if x > 5:\n"
            "        pass\n"
            "    if x > 6:\n"
            "        pass\n"
        )
        result = scan_file_for_anti_patterns(source, "test.py")
        assert len(result) == 2
        assert result[0]["priority"] == 1
        assert result[1]["priority"] == 3


class TestScanFileForAntiPatternsAsync:
    def test_handles_async_functions(self):
        source = (
            "async def foo():\n"
            "    try:\n"
            "        try:\n"
            "            pass\n"
            "        except Exception:\n"
            "            pass\n"
            "    except Exception:\n"
            "        pass\n"
        )
        result = scan_file_for_anti_patterns(source, "test.py")
        assert len(result) == 1
        assert result[0]["function_name"] == "foo"
        assert result[0]["priority"] == 1


class TestScanFileForAntiPatternsInvalidSource:
    def test_empty_source_returns_empty_list(self):
        result = scan_file_for_anti_patterns("", "test.py")
        assert result == []

    def test_invalid_source_returns_empty_list(self):
        result = scan_file_for_anti_patterns("def foo(: invalid", "test.py")
        assert result == []


# ── virtual_ast_buffer tests ────────────────────────────────────────────────

class TestVirtualASTBufferReplaceFunction:
    def test_replaces_top_level_function(self):
        source = "def foo():\n    return 1\n"
        buf = VirtualASTBuffer(source, "test.py")
        new_src = buf.replace_function("foo", "def foo():\n    return 2\n")
        assert "return 2" in new_src
        assert "return 1" not in new_src

    def test_replaces_method_inside_class(self):
        source = (
            "class Foo:\n"
            "    def bar(self):\n"
            "        return 1\n"
        )
        buf = VirtualASTBuffer(source, "test.py")
        new_src = buf.replace_function("bar", "def bar(self):\n    return 2\n")
        assert "return 2" in new_src
        assert "return 1" not in new_src

    def test_raises_value_error_when_function_not_found(self):
        source = "def foo():\n    return 1\n"
        buf = VirtualASTBuffer(source, "test.py")
        with pytest.raises(ValueError, match="not found"):
            buf.replace_function("nonexistent", "def nonexistent():\n    pass\n")

    def test_replaces_method_in_nested_class(self):
        source = (
            "class Outer:\n"
            "    class Inner:\n"
            "        def method(self):\n"
            "            return 1\n"
        )
        buf = VirtualASTBuffer(source, "test.py")
        new_src = buf.replace_function("method", "def method(self):\n    return 2\n")
        assert "return 2" in new_src
        assert "return 1" not in new_src

    def test_replaces_deeply_nested_class_method(self):
        source = (
            "class A:\n"
            "    class B:\n"
            "        class C:\n"
            "            def deep(self):\n"
            "                return 1\n"
        )
        buf = VirtualASTBuffer(source, "test.py")
        new_src = buf.replace_function("deep", "def deep(self):\n    return 2\n")
        assert "return 2" in new_src
        assert "return 1" not in new_src


class TestVirtualASTBufferInjectHelper:
    def test_injects_before_anchor_function(self):
        source = "def foo():\n    return 1\n\ndef bar():\n    return 2\n"
        buf = VirtualASTBuffer(source, "test.py")
        new_src = buf.inject_helper("def helper():\n    pass\n", anchor_function="bar")
        lines = new_src.splitlines()
        helper_idx = next(i for i, l in enumerate(lines) if "def helper" in l)
        bar_idx = next(i for i, l in enumerate(lines) if "def bar" in l)
        assert helper_idx < bar_idx

    def test_appends_when_no_anchor(self):
        source = "def foo():\n    return 1\n"
        buf = VirtualASTBuffer(source, "test.py")
        new_src = buf.inject_helper("def helper():\n    pass\n")
        assert "def helper" in new_src


class TestVirtualASTBufferGetSource:
    def test_get_source_returns_current_source(self):
        source = "def foo():\n    return 1\n"
        buf = VirtualASTBuffer(source, "test.py")
        assert buf.get_source() == source


class TestEnsurePydanticImports:
    def test_adds_pydantic_import_when_needed(self):
        source = "def foo():\n    pass\n"
        refactored = "def foo():\n    return BaseModel()\n"
        result = ensure_pydantic_imports(source, refactored)
        assert "from pydantic import BaseModel" in result

    def test_does_not_duplicate_existing_pydantic_import(self):
        source = "from pydantic import BaseModel\n\ndef foo():\n    pass\n"
        refactored = "def foo():\n    return BaseModel()\n"
        result = ensure_pydantic_imports(source, refactored)
        count = result.count("from pydantic import BaseModel")
        assert count == 1


# ── ast_verifier tests ──────────────────────────────────────────────────────

class TestVerifyRefactoredAst:
    def test_passes_for_clean_refactored_code(self):
        orig = "def foo(x):\n    return x + 1\n"
        refactored = "def foo(x):\n    return x + 1\n"
        passed, cc, depth, msg = verify_refactored_ast(refactored, candidate_name="foo", orig_code=orig)
        assert passed is True

    def test_fails_for_syntax_errors(self):
        refactored = "def foo(: invalid\n"
        passed, cc, depth, msg = verify_refactored_ast(refactored)
        assert passed is False
        assert "SyntaxError" in msg

    def test_fails_for_unauthorized_imports(self):
        orig = "def foo():\n    pass\n"
        refactored = "import os\ndef foo():\n    pass\n"
        passed, cc, depth, msg = verify_refactored_ast(refactored, candidate_name="foo", orig_code=orig)
        assert passed is False
        assert "unauthorized_import" in msg

    def test_fails_for_class_creation(self):
        orig = "def foo():\n    pass\n"
        refactored = "class NewClass:\n    pass\n\ndef foo():\n    pass\n"
        passed, cc, depth, msg = verify_refactored_ast(refactored, candidate_name="foo", orig_code=orig)
        assert passed is False
        assert "unauthorized_symbol" in msg

    def test_fails_for_nested_functions(self):
        orig = "def foo():\n    pass\n"
        refactored = (
            "def foo():\n"
            "    def inner():\n"
            "        pass\n"
        )
        passed, cc, depth, msg = verify_refactored_ast(refactored, candidate_name="foo", orig_code=orig)
        assert passed is False
        assert "invalid_helper_name" in msg

    def test_fails_for_helper_not_starting_with_underscore(self):
        orig = "def foo():\n    pass\n"
        refactored = (
            "def foo():\n"
            "    pass\n"
            "\n"
            "def helper():\n"
            "    pass\n"
        )
        passed, cc, depth, msg = verify_refactored_ast(refactored, candidate_name="foo", orig_code=orig)
        assert passed is False
        assert "invalid_helper_name" in msg

    def test_fails_for_hallucinated_attributes(self):
        orig = "def foo():\n    x = obj.attr\n"
        refactored = "def foo():\n    x = obj.nonexistent_attr\n"
        passed, cc, depth, msg = verify_refactored_ast(refactored, candidate_name="foo", orig_code=orig)
        assert passed is False
        assert "hallucinated_fields" in msg

    def test_fails_for_argument_swaps(self):
        orig = "def foo():\n    result = func(a, b)\n"
        refactored = "def foo():\n    result = func(b, a)\n"
        passed, cc, depth, msg = verify_refactored_ast(refactored, candidate_name="foo", orig_code=orig)
        assert passed is False
        assert "argument_swap" in msg

    def test_fails_for_signature_mismatches(self):
        orig = "def foo(x, y):\n    return x + y\n"
        refactored = "def foo(x):\n    return x\n"
        passed, cc, depth, msg = verify_refactored_ast(refactored, candidate_name="foo", orig_code=orig)
        assert passed is False
        assert "signature_mismatch" in msg

    def test_fails_for_unimported_symbols(self):
        orig = "def foo():\n    pass\n"
        refactored = "def foo():\n    x = undefined_symbol\n"
        passed, cc, depth, msg = verify_refactored_ast(refactored, candidate_name="foo", orig_code=orig)
        assert passed is False
        assert "unimported_symbol" in msg

    def test_fails_for_cc_greater_than_5(self):
        orig = "def foo():\n    pass\n"
        refactored = (
            "def foo():\n"
            "    if True:\n"
            "        pass\n"
            "    if True:\n"
            "        pass\n"
            "    if True:\n"
            "        pass\n"
            "    if True:\n"
            "        pass\n"
            "    if True:\n"
            "        pass\n"
            "    if True:\n"
            "        pass\n"
        )
        passed, cc, depth, msg = verify_refactored_ast(refactored, candidate_name="foo", orig_code=orig)
        assert passed is False
        assert "cc_exceeds" in msg

    def test_fails_for_nesting_depth_greater_than_3(self):
        orig = "def foo():\n    pass\n"
        refactored = (
            "def foo():\n"
            "    if True:\n"
            "        if True:\n"
            "            if True:\n"
            "                if True:\n"
            "                    pass\n"
        )
        passed, cc, depth, msg = verify_refactored_ast(refactored, candidate_name="foo", orig_code=orig)
        assert passed is False
        assert "nesting_exceeds" in msg

    def test_fails_for_try_pyramids(self):
        orig = "def foo():\n    pass\n"
        refactored = (
            "def foo():\n"
            "    try:\n"
            "        try:\n"
            "            pass\n"
            "        except Exception:\n"
            "            pass\n"
            "    except Exception:\n"
            "        pass\n"
        )
        passed, cc, depth, msg = verify_refactored_ast(refactored, candidate_name="foo", orig_code=orig)
        assert passed is False
        assert "try_pyramid" in msg


class TestRunLintRegression:
    def test_passes_when_no_new_errors(self):
        orig = "def foo():\n    return 1\n"
        refactored = "def foo():\n    return 2\n"
        passed, msg = run_lint_regression(orig, refactored)
        assert passed is True

    def test_detects_new_ruff_errors(self):
        orig = "def foo():\n    return 1\n"
        refactored = "def foo():\n    x = undefined_name\n    return 1\n"
        passed, msg = run_lint_regression(orig, refactored)
        assert passed is False


class TestExtractHeaderSymbolContract:
    def test_extracts_imports_symbols_defs_globals(self):
        source = (
            "import os\n"
            "from typing import List\n"
            "\n"
            "CONST = 42\n"
            "\n"
            "def foo():\n"
            "    pass\n"
            "\n"
            "class Bar:\n"
            "    pass\n"
        )
        contract = extract_header_symbol_contract(source)
        assert "os" in contract["imported_modules"]
        assert "typing" in contract["imported_modules"]
        assert "List" in contract["imported_symbols"]
        assert "foo" in contract["top_level_symbols"]
        assert "Bar" in contract["top_level_symbols"]
        assert "CONST" in contract["global_constants"]

    def test_empty_source_returns_empty_contract(self):
        contract = extract_header_symbol_contract("")
        assert contract == {"imported_modules": [], "imported_symbols": [], "top_level_symbols": [], "global_constants": []}

    def test_invalid_source_returns_empty_contract(self):
        contract = extract_header_symbol_contract("def (: invalid")
        assert contract == {"imported_modules": [], "imported_symbols": [], "top_level_symbols": [], "global_constants": []}


class TestSymbolScopeVisitor:
    def test_detects_unimported_symbols(self):
        source = "import os\n\ndef foo():\n    x = undefined_var\n"
        contract = extract_header_symbol_contract(source)
        tree = ast.parse(source)
        visitor = SymbolScopeVisitor(contract, source)
        violations = visitor.inspect(tree)
        names = [v["name"] for v in violations]
        assert "undefined_var" in names

    def test_detects_unimported_function_calls(self):
        source = "import os\n\ndef foo():\n    unknown_func()\n"
        contract = extract_header_symbol_contract(source)
        tree = ast.parse(source)
        visitor = SymbolScopeVisitor(contract, source)
        violations = visitor.inspect(tree)
        names = [v["name"] for v in violations]
        assert "unknown_func" in names

    def test_allows_imported_symbols(self):
        source = "import os\n\ndef foo():\n    x = os.path\n"
        contract = extract_header_symbol_contract(source)
        tree = ast.parse(source)
        visitor = SymbolScopeVisitor(contract, source)
        violations = visitor.inspect(tree)
        assert len(violations) == 0

    def test_walrus_operator_adds_target_to_scope(self):
        source = "import os\n\ndef foo():\n    if (x := len(os.listdir('.'))) > 0:\n        pass\n"
        contract = extract_header_symbol_contract(source)
        tree = ast.parse(source)
        visitor = SymbolScopeVisitor(contract, source)
        violations = visitor.inspect(tree)
        assert len(violations) == 0

    def test_walrus_operator_detects_unimported_target(self):
        source = "def foo():\n    if (x := undefined_var) > 0:\n        pass\n"
        contract = extract_header_symbol_contract(source)
        tree = ast.parse(source)
        visitor = SymbolScopeVisitor(contract, source)
        violations = visitor.inspect(tree)
        names = [v["name"] for v in violations]
        assert "undefined_var" in names

    def test_starred_expression_checks_value(self):
        source = "def foo():\n    x = [undefined_var]\n    for item in x:\n        pass\n"
        contract = extract_header_symbol_contract(source)
        tree = ast.parse(source)
        visitor = SymbolScopeVisitor(contract, source)
        violations = visitor.inspect(tree)
        names = [v["name"] for v in violations]
        assert "undefined_var" in names


class TestComplexityVisitor:
    def test_counts_if(self):
        source = "def foo():\n    if True:\n        pass\n"
        tree = ast.parse(source)
        fn = tree.body[0]
        vis = VerifierComplexityVisitor()
        vis.visit(fn)
        assert vis.complexity == 2

    def test_counts_for(self):
        source = "def foo():\n    for x in []:\n        pass\n"
        tree = ast.parse(source)
        fn = tree.body[0]
        vis = VerifierComplexityVisitor()
        vis.visit(fn)
        assert vis.complexity == 2

    def test_counts_while(self):
        source = "def foo():\n    while True:\n        pass\n"
        tree = ast.parse(source)
        fn = tree.body[0]
        vis = VerifierComplexityVisitor()
        vis.visit(fn)
        assert vis.complexity == 2

    def test_counts_try(self):
        source = "def foo():\n    try:\n        pass\n    except:\n        pass\n"
        tree = ast.parse(source)
        fn = tree.body[0]
        vis = VerifierComplexityVisitor()
        vis.visit(fn)
        assert vis.complexity == 2

    def test_counts_with(self):
        source = "def foo():\n    with open('x') as f:\n        pass\n"
        tree = ast.parse(source)
        fn = tree.body[0]
        vis = VerifierComplexityVisitor()
        vis.visit(fn)
        assert vis.complexity == 2

    def test_counts_boolop(self):
        source = "def foo():\n    if a and b:\n        pass\n"
        tree = ast.parse(source)
        fn = tree.body[0]
        vis = VerifierComplexityVisitor()
        vis.visit(fn)
        assert vis.complexity == 3

    def test_counts_nested_structures(self):
        source = (
            "def foo():\n"
            "    if True:\n"
            "        for x in []:\n"
            "            while True:\n"
            "                try:\n"
            "                    pass\n"
            "                except:\n"
            "                    pass\n"
        )
        tree = ast.parse(source)
        fn = tree.body[0]
        vis = VerifierComplexityVisitor()
        vis.visit(fn)
        assert vis.complexity == 5

    def test_counts_ifexp(self):
        source = "def foo():\n    x = 1 if True else 2\n"
        tree = ast.parse(source)
        fn = tree.body[0]
        vis = VerifierComplexityVisitor()
        vis.visit(fn)
        assert vis.complexity == 2

    def test_counts_assert(self):
        source = "def foo():\n    assert True\n"
        tree = ast.parse(source)
        fn = tree.body[0]
        vis = VerifierComplexityVisitor()
        vis.visit(fn)
        assert vis.complexity == 2

    def test_base_complexity_is_1(self):
        source = "def foo():\n    return 1\n"
        tree = ast.parse(source)
        fn = tree.body[0]
        vis = VerifierComplexityVisitor()
        vis.visit(fn)
        assert vis.complexity == 1

    @pytest.mark.skipif(not hasattr(ast, 'AsyncGeneratorExp'), reason="AsyncGeneratorExp not available")
    def test_counts_async_generator_exp(self):
        source = "def foo():\n    x = (y async for y in [])\n"
        tree = ast.parse(source)
        fn = tree.body[0]
        vis = VerifierComplexityVisitor()
        vis.visit(fn)
        assert vis.complexity == 2

    @pytest.mark.skipif(not hasattr(ast, 'ExceptGroup'), reason="ExceptGroup not available")
    def test_counts_except_group(self):
        source = "def foo():\n    try:\n        pass\n    except* Exception:\n        pass\n"
        tree = ast.parse(source)
        fn = tree.body[0]
        vis = VerifierComplexityVisitor()
        vis.visit(fn)
        assert vis.complexity == 2