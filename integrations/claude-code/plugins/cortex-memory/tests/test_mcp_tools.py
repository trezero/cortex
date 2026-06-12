"""Tests for the plugin MCP tools (smart_search, smart_outline, smart_unfold).

Tools are tested directly by calling the underlying logic functions,
with the parser/search layer mocked.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.smart_explore.parser import CodeSymbol, ParsedFile
from src.smart_explore.search import SearchResult


# ── Fixtures ───────────────────────────────────────────────────────────────────


def _make_symbol(name: str, kind: str = "function", line_start: int = 1, line_end: int = 5) -> CodeSymbol:
    return CodeSymbol(
        name=name,
        kind=kind,
        line_start=line_start,
        line_end=line_end,
        signature=f"def {name}():",
        docstring=f"Docstring for {name}",
    )


def _make_parsed_file(path: str = "src/parser.py") -> ParsedFile:
    return ParsedFile(
        path=path,
        language="python",
        symbols=[
            _make_symbol("parse_file", line_start=1, line_end=10),
            _make_symbol("walk_directory", line_start=12, line_end=20),
        ],
        imports=[],
        line_count=30,
    )


def _make_search_result(num_symbols: int = 2) -> SearchResult:
    pf = _make_parsed_file()
    symbols = [(pf.symbols[i % len(pf.symbols)], 10 - i, f"name:{'exact' if i == 0 else 'substring'}") for i in range(num_symbols)]
    return SearchResult(
        matching_symbols=symbols,
        folded_files=[pf],
        stats={"files_scanned": 3, "files_parsed": 2, "symbols_found": 5},
        token_estimate=200,
    )


# ── Import the tool functions ──────────────────────────────────────────────────


def test_mcp_server_module_importable():
    """The mcp_server module can be imported without errors."""
    import importlib
    mod = importlib.import_module("src.mcp_server")
    assert mod is not None


def test_mcp_server_exposes_mcp_instance():
    """mcp_server exposes a FastMCP instance named 'mcp'."""
    from src.mcp_server import mcp
    assert mcp is not None
    assert hasattr(mcp, "tool")


# ── smart_search ───────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_smart_search_returns_string():
    """smart_search returns a non-empty string."""
    from src.mcp_server import _smart_search_impl

    result = _make_search_result(2)
    with patch("src.mcp_server.search_codebase", return_value=result):
        output = await _smart_search_impl(query="parse", path="/some/dir")

    assert isinstance(output, str)
    assert len(output) > 0


@pytest.mark.anyio
async def test_smart_search_includes_symbol_name():
    """smart_search output includes matched symbol names."""
    from src.mcp_server import _smart_search_impl

    result = _make_search_result(2)
    with patch("src.mcp_server.search_codebase", return_value=result):
        output = await _smart_search_impl(query="parse", path="/some/dir")

    assert "parse_file" in output


@pytest.mark.anyio
async def test_smart_search_no_results_returns_helpful_message():
    """smart_search with no matches returns an informative message."""
    from src.mcp_server import _smart_search_impl

    empty_result = SearchResult(
        matching_symbols=[],
        folded_files=[],
        stats={"files_scanned": 5, "files_parsed": 5, "symbols_found": 0},
        token_estimate=0,
    )
    with patch("src.mcp_server.search_codebase", return_value=empty_result):
        output = await _smart_search_impl(query="xyzzy", path="/some/dir")

    assert isinstance(output, str)
    assert any(word in output.lower() for word in ["no", "0", "found"])


@pytest.mark.anyio
async def test_smart_search_uses_cwd_when_no_path():
    """smart_search uses os.getcwd() when path is None."""
    import os
    from src.mcp_server import _smart_search_impl

    empty_result = SearchResult(matching_symbols=[], folded_files=[], stats={}, token_estimate=0)
    with patch("src.mcp_server.search_codebase", return_value=empty_result) as mock_search:
        await _smart_search_impl(query="foo", path=None)

    called_root = mock_search.call_args[0][0]
    assert called_root == os.getcwd()


@pytest.mark.anyio
async def test_smart_search_passes_max_results():
    """smart_search passes max_results to search_codebase."""
    from src.mcp_server import _smart_search_impl

    empty_result = SearchResult(matching_symbols=[], folded_files=[], stats={}, token_estimate=0)
    with patch("src.mcp_server.search_codebase", return_value=empty_result) as mock_search:
        await _smart_search_impl(query="foo", path="/some/dir", max_results=5)

    _, kwargs = mock_search.call_args
    assert kwargs.get("max_results") == 5 or mock_search.call_args[0][2] == 5


# ── smart_outline ──────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_smart_outline_returns_file_structure():
    """smart_outline returns a structural view of the file."""
    from src.mcp_server import _smart_outline_impl

    pf = _make_parsed_file("src/parser.py")
    content = "def parse_file(): pass\n" * 30

    with patch("src.mcp_server.parse_file", return_value=pf), \
         patch("src.mcp_server._read_file", return_value=content):
        output = await _smart_outline_impl(file_path="src/parser.py")

    assert isinstance(output, str)
    assert "parse_file" in output


@pytest.mark.anyio
async def test_smart_outline_includes_line_numbers():
    """smart_outline includes line number info."""
    from src.mcp_server import _smart_outline_impl

    pf = _make_parsed_file("src/parser.py")
    content = "def parse_file(): pass\n" * 30

    with patch("src.mcp_server.parse_file", return_value=pf), \
         patch("src.mcp_server._read_file", return_value=content):
        output = await _smart_outline_impl(file_path="src/parser.py")

    assert any(char.isdigit() for char in output)


@pytest.mark.anyio
async def test_smart_outline_unsupported_language_returns_error():
    """smart_outline returns an error message for unsupported file types."""
    from src.mcp_server import _smart_outline_impl

    with patch("src.mcp_server.parse_file", return_value=None), \
         patch("src.mcp_server._read_file", return_value="a,b,c"):
        output = await _smart_outline_impl(file_path="data.csv")

    assert "unsupported" in output.lower() or "cannot" in output.lower() or "not" in output.lower()


# ── smart_unfold ───────────────────────────────────────────────────────────────


SAMPLE_CONTENT = """\
def parse_file(path, content):
    \"\"\"Parse a source file.\"\"\"
    return None


def walk_directory(root):
    yield root
"""


@pytest.mark.anyio
async def test_smart_unfold_returns_symbol_source():
    """smart_unfold returns the full source of the requested symbol."""
    from src.mcp_server import _smart_unfold_impl

    pf = _make_parsed_file("parser.py")

    with patch("src.mcp_server.parse_file", return_value=pf), \
         patch("src.mcp_server._read_file", return_value=SAMPLE_CONTENT):
        output = await _smart_unfold_impl(file_path="parser.py", symbol_name="parse_file")

    assert "parse_file" in output


@pytest.mark.anyio
async def test_smart_unfold_includes_location_info():
    """smart_unfold includes file path and line number in output."""
    from src.mcp_server import _smart_unfold_impl

    pf = _make_parsed_file("parser.py")

    with patch("src.mcp_server.parse_file", return_value=pf), \
         patch("src.mcp_server._read_file", return_value=SAMPLE_CONTENT):
        output = await _smart_unfold_impl(file_path="parser.py", symbol_name="parse_file")

    assert "parser.py" in output
    assert any(char.isdigit() for char in output)


@pytest.mark.anyio
async def test_smart_unfold_unknown_symbol_lists_available():
    """smart_unfold with nonexistent symbol lists available symbols."""
    from src.mcp_server import _smart_unfold_impl

    pf = _make_parsed_file("parser.py")

    with patch("src.mcp_server.parse_file", return_value=pf), \
         patch("src.mcp_server._read_file", return_value=SAMPLE_CONTENT):
        output = await _smart_unfold_impl(file_path="parser.py", symbol_name="nonexistent_xyz")

    assert "nonexistent_xyz" in output or "not found" in output.lower()
    # Should list available symbols
    assert "parse_file" in output or "walk_directory" in output


@pytest.mark.anyio
async def test_smart_unfold_unsupported_file_returns_error():
    """smart_unfold returns an error for unsupported file types."""
    from src.mcp_server import _smart_unfold_impl

    with patch("src.mcp_server.parse_file", return_value=None), \
         patch("src.mcp_server._read_file", return_value="a,b,c"):
        output = await _smart_unfold_impl(file_path="data.csv", symbol_name="foo")

    assert "unsupported" in output.lower() or "cannot" in output.lower() or "not" in output.lower()
