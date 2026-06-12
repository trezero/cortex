"""Tests for search and ranking in smart-explore."""

import os
import pytest
from pathlib import Path
from src.smart_explore.parser import CodeSymbol, ParsedFile
from src.smart_explore.search import (
    SearchResult,
    format_folded_view,
    format_search_results,
    format_unfold,
    match_score,
    rank_symbols,
    search_codebase,
    walk_directory,
)


# ── walk_directory ─────────────────────────────────────────────────────────────


def test_walk_directory_finds_python_files(tmp_path):
    (tmp_path / "main.py").write_text("def hello(): pass")
    (tmp_path / "utils.py").write_text("def helper(): pass")
    (tmp_path / "README.md").write_text("# docs")

    files = walk_directory(str(tmp_path))
    basenames = [os.path.basename(f) for f in files]
    assert "main.py" in basenames
    assert "utils.py" in basenames
    assert "README.md" not in basenames  # not a code file


def test_walk_directory_finds_typescript_files(tmp_path):
    (tmp_path / "index.ts").write_text("export const x = 1;")
    (tmp_path / "App.tsx").write_text("export default function App() {}")

    files = walk_directory(str(tmp_path))
    basenames = [os.path.basename(f) for f in files]
    assert "index.ts" in basenames
    assert "App.tsx" in basenames


def test_walk_directory_skips_node_modules(tmp_path):
    nm = tmp_path / "node_modules" / "lodash"
    nm.mkdir(parents=True)
    (nm / "index.js").write_text("module.exports = {};")
    (tmp_path / "app.js").write_text("const lo = require('lodash');")

    files = walk_directory(str(tmp_path))
    paths = [f for f in files if "node_modules" in f]
    assert paths == []


def test_walk_directory_skips_git(tmp_path):
    git_dir = tmp_path / ".git" / "hooks"
    git_dir.mkdir(parents=True)
    (git_dir / "pre-commit").write_text("#!/bin/sh")
    (tmp_path / "src.py").write_text("x = 1")

    files = walk_directory(str(tmp_path))
    paths = [f for f in files if ".git" in f]
    assert paths == []


def test_walk_directory_skips_pycache(tmp_path):
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "module.cpython-313.pyc").write_bytes(b"\x00" * 10)
    (tmp_path / "module.py").write_text("x = 1")

    files = walk_directory(str(tmp_path))
    paths = [f for f in files if "__pycache__" in f]
    assert paths == []


def test_walk_directory_recurses_into_subdirectories(tmp_path):
    sub = tmp_path / "src" / "utils"
    sub.mkdir(parents=True)
    (sub / "helpers.py").write_text("def help(): pass")

    files = walk_directory(str(tmp_path))
    assert any("helpers.py" in f for f in files)


def test_walk_directory_skips_files_over_512kb(tmp_path):
    big = tmp_path / "huge.py"
    big.write_bytes(b"x = 1\n" * 100_000)  # ~600KB
    small = tmp_path / "small.py"
    small.write_text("x = 1")

    files = walk_directory(str(tmp_path))
    assert not any("huge.py" in f for f in files)
    assert any("small.py" in f for f in files)


def test_walk_directory_skips_venv(tmp_path):
    venv = tmp_path / ".venv" / "lib" / "python3.12"
    venv.mkdir(parents=True)
    (venv / "site.py").write_text("x = 1")
    (tmp_path / "main.py").write_text("x = 1")

    files = walk_directory(str(tmp_path))
    paths = [f for f in files if ".venv" in f]
    assert paths == []


# ── match_score ────────────────────────────────────────────────────────────────


def test_match_score_exact_match_highest():
    score = match_score("parse_file", ["parse_file"])
    assert score >= 10


def test_match_score_substring_match():
    score = match_score("parse_file_content", ["parse_file"])
    assert 1 <= score < 10


def test_match_score_no_match_zero():
    score = match_score("unrelated_function", ["xyz_nothing"])
    assert score == 0


def test_match_score_exact_beats_substring():
    exact = match_score("greet", ["greet"])
    substr = match_score("greeter_factory", ["greet"])
    assert exact > substr


def test_match_score_multiple_query_parts():
    score = match_score("parse_python_file", ["parse", "python"])
    assert score > match_score("parse_python_file", ["parse"])


def test_match_score_case_insensitive():
    score_lower = match_score("ParseFile", ["parsefile"])
    assert score_lower > 0


# ── rank_symbols ───────────────────────────────────────────────────────────────


def _make_symbol(name: str, kind: str = "function", signature: str = "", docstring: str | None = None) -> CodeSymbol:
    return CodeSymbol(
        name=name,
        kind=kind,
        line_start=1,
        line_end=10,
        signature=signature,
        docstring=docstring,
    )


def test_rank_symbols_returns_list_of_tuples():
    symbols = [_make_symbol("greet"), _make_symbol("parse")]
    results = rank_symbols(symbols, "greet")
    assert isinstance(results, list)
    for item in results:
        assert len(item) == 3  # (symbol, score, reason)


def test_rank_symbols_name_match_scores_highest():
    exact_name = _make_symbol("parse_file", signature="def parse_file(path): ...")
    sig_match = _make_symbol("process_data", signature="def process_data(parse_file): ...")
    results = rank_symbols([exact_name, sig_match], "parse_file")
    scored = [(sym.name, score) for sym, score, _ in results]
    # find scores
    name_score = next(score for name, score in scored if name == "parse_file")
    sig_score = next(score for name, score in scored if name == "process_data")
    assert name_score > sig_score


def test_rank_symbols_filters_zero_scores():
    symbols = [
        _make_symbol("greet", docstring="Say hello"),
        _make_symbol("unrelated_xyz"),
    ]
    results = rank_symbols(symbols, "greet")
    names = [sym.name for sym, _, _ in results]
    assert "greet" in names
    assert "unrelated_xyz" not in names


def test_rank_symbols_docstring_contributes_score():
    no_doc = _make_symbol("func_a", docstring=None)
    with_doc = _make_symbol("func_b", docstring="Parse and validate input")
    results = rank_symbols([no_doc, with_doc], "parse")
    doc_score = next((score for sym, score, _ in results if sym.name == "func_b"), 0)
    assert doc_score > 0


def test_rank_symbols_sorted_by_score_descending():
    symbols = [
        _make_symbol("helper"),
        _make_symbol("parse_helper", docstring="Helps parse files"),
        _make_symbol("parse_file"),
    ]
    results = rank_symbols(symbols, "parse")
    scores = [score for _, score, _ in results]
    assert scores == sorted(scores, reverse=True)


def test_rank_symbols_includes_match_reason():
    sym = _make_symbol("parse_file", docstring="Parse a source file")
    results = rank_symbols([sym], "parse")
    assert len(results) == 1
    _, _, reason = results[0]
    assert isinstance(reason, str)
    assert len(reason) > 0


# ── format_folded_view ─────────────────────────────────────────────────────────


def _make_parsed_file(path: str = "example.py") -> ParsedFile:
    greet = CodeSymbol(
        name="greet",
        kind="function",
        line_start=3,
        line_end=5,
        signature="def greet(name: str) -> str:",
        docstring="Return greeting",
    )
    greeter = CodeSymbol(
        name="Greeter",
        kind="class",
        line_start=8,
        line_end=20,
        signature="class Greeter:",
        docstring="A greeter class",
        children=[
            CodeSymbol(name="__init__", kind="method", line_start=10, line_end=12, signature="def __init__(self):", parent="Greeter"),
            CodeSymbol(name="greet", kind="method", line_start=14, line_end=16, signature="def greet(self, name):", parent="Greeter"),
        ],
    )
    return ParsedFile(path=path, language="python", symbols=[greet, greeter], imports=[], line_count=20)


def test_format_folded_view_includes_file_path():
    pf = _make_parsed_file("src/example.py")
    output = format_folded_view(pf)
    assert "src/example.py" in output or "example.py" in output


def test_format_folded_view_includes_symbol_names():
    pf = _make_parsed_file()
    output = format_folded_view(pf)
    assert "greet" in output
    assert "Greeter" in output


def test_format_folded_view_includes_line_numbers():
    pf = _make_parsed_file()
    output = format_folded_view(pf)
    assert "3" in output or "L3" in output  # greet starts at line 3


def test_format_folded_view_shows_class_children():
    pf = _make_parsed_file()
    output = format_folded_view(pf)
    assert "__init__" in output
    assert "greet" in output  # both top-level and method


def test_format_folded_view_shows_signatures():
    pf = _make_parsed_file()
    output = format_folded_view(pf)
    assert "def greet" in output or "greet(name" in output


# ── format_search_results ──────────────────────────────────────────────────────


def _make_search_result() -> SearchResult:
    sym = CodeSymbol(
        name="parse_file",
        kind="function",
        line_start=10,
        line_end=30,
        signature="def parse_file(path: str, content: str) -> ParsedFile:",
        docstring="Parse a source file.",
    )
    parsed = ParsedFile(path="src/parser.py", language="python", symbols=[sym], imports=[], line_count=100)
    return SearchResult(
        matching_symbols=[(sym, 25, "name:exact"), (sym, 10, "signature:substring")],
        folded_files=[parsed],
        stats={"files_scanned": 5, "files_parsed": 4, "symbols_found": 10},
        token_estimate=500,
    )


def test_format_search_results_includes_query_matches():
    result = _make_search_result()
    output = format_search_results(result)
    assert "parse_file" in output


def test_format_search_results_includes_file_path():
    result = _make_search_result()
    output = format_search_results(result)
    assert "src/parser.py" in output or "parser.py" in output


def test_format_search_results_includes_stats():
    result = _make_search_result()
    output = format_search_results(result)
    # Should mention some stats (files scanned, symbols, etc.)
    assert any(word in output.lower() for word in ["file", "symbol", "result", "match"])


def test_format_search_results_empty_shows_no_results():
    result = SearchResult(
        matching_symbols=[],
        folded_files=[],
        stats={"files_scanned": 3, "files_parsed": 3, "symbols_found": 0},
        token_estimate=0,
    )
    output = format_search_results(result)
    assert "no" in output.lower() or "0" in output or "found" in output.lower()


# ── format_unfold ──────────────────────────────────────────────────────────────


SAMPLE_LINES = [
    "# module header",
    "",
    "def parse_file(path, content):",
    '    """Parse a source file."""',
    "    return None",
    "",
    "def other(): pass",
]


def test_format_unfold_includes_symbol_source():
    sym = CodeSymbol(name="parse_file", kind="function", line_start=3, line_end=5, signature="def parse_file(path, content):")
    output = format_unfold("parser.py", sym, SAMPLE_LINES)
    assert "def parse_file" in output


def test_format_unfold_includes_file_and_line_info():
    sym = CodeSymbol(name="parse_file", kind="function", line_start=3, line_end=5, signature="def parse_file(path, content):")
    output = format_unfold("parser.py", sym, SAMPLE_LINES)
    assert "parser.py" in output
    assert "3" in output  # line number


def test_format_unfold_does_not_include_other_symbols():
    sym = CodeSymbol(name="parse_file", kind="function", line_start=3, line_end=5, signature="def parse_file(path, content):")
    output = format_unfold("parser.py", sym, SAMPLE_LINES)
    # Should not show "other" function which is outside this symbol's range
    assert "def other" not in output


# ── search_codebase ────────────────────────────────────────────────────────────


PYTHON_SAMPLE = '''\
def parse_file(path: str, content: str):
    """Parse a source file into symbols."""
    return None


def walk_directory(root: str):
    """Walk directory and yield code paths."""
    yield root


class CodeParser:
    """Main parser class."""

    def run(self, path: str):
        """Execute parsing."""
        return self.parse(path)
'''


def test_search_codebase_finds_matching_symbols(tmp_path):
    (tmp_path / "parser.py").write_text(PYTHON_SAMPLE)
    result = search_codebase(str(tmp_path), "parse")
    names = [sym.name for sym, _, _ in result.matching_symbols]
    assert "parse_file" in names


def test_search_codebase_returns_search_result_type(tmp_path):
    (tmp_path / "parser.py").write_text(PYTHON_SAMPLE)
    result = search_codebase(str(tmp_path), "parse")
    assert isinstance(result, SearchResult)
    assert hasattr(result, "matching_symbols")
    assert hasattr(result, "folded_files")
    assert hasattr(result, "stats")
    assert hasattr(result, "token_estimate")


def test_search_codebase_stats_reflect_files_scanned(tmp_path):
    (tmp_path / "a.py").write_text("def foo(): pass")
    (tmp_path / "b.py").write_text("def bar(): pass")
    result = search_codebase(str(tmp_path), "foo")
    assert result.stats["files_scanned"] >= 2


def test_search_codebase_skips_unreadable_ignored_dirs(tmp_path):
    nm = tmp_path / "node_modules" / "pkg"
    nm.mkdir(parents=True)
    (nm / "index.js").write_text("function parse() {}")
    (tmp_path / "app.py").write_text("def parse(): pass")

    result = search_codebase(str(tmp_path), "parse")
    # Should only find app.py's symbol, not node_modules
    for sym, _, _ in result.matching_symbols:
        assert "node_modules" not in getattr(sym, "file_path", "")


def test_search_codebase_respects_max_results(tmp_path):
    # Create file with many matching symbols
    content = "\n".join(f"def parse_{i}(): pass" for i in range(30))
    (tmp_path / "many.py").write_text(content)

    result = search_codebase(str(tmp_path), "parse", max_results=5)
    assert len(result.matching_symbols) <= 5


def test_search_codebase_no_results_returns_empty(tmp_path):
    (tmp_path / "app.py").write_text("def hello(): pass")
    result = search_codebase(str(tmp_path), "xyzzy_nonexistent")
    assert result.matching_symbols == []
