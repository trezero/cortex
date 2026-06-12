"""Cortex Memory Plugin — MCP server.

Exposes three tools to the AI IDE:
- smart_search: Find symbols across a codebase using tree-sitter AST parsing
- smart_outline: Get a structural overview of a single file
- smart_unfold: Expand a specific symbol to its full source

Run as a subprocess via stdio transport:
    python -m src.mcp_server
"""

from __future__ import annotations

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .smart_explore.parser import parse_file
from .smart_explore.search import (
    SearchResult,
    format_folded_view,
    format_search_results,
    format_unfold,
    search_codebase,
)

mcp = FastMCP("cortex-memory")


def _read_file(file_path: str) -> str:
    """Read a file, returning its content as a string."""
    return Path(file_path).read_text(encoding="utf-8", errors="replace")


def _find_symbol(parsed, name: str):
    """Search parsed file symbols (and children) for the named symbol."""
    for sym in parsed.symbols:
        if sym.name == name:
            return sym
        for child in sym.children:
            if child.name == name:
                return child
    return None


async def _smart_search_impl(
    query: str,
    path: str | None = None,
    max_results: int = 20,
    file_pattern: str | None = None,
) -> str:
    root = path or os.getcwd()
    result = search_codebase(root, query, max_results=max_results, file_pattern=file_pattern)
    return format_search_results(result)


async def _smart_outline_impl(file_path: str) -> str:
    try:
        content = _read_file(file_path)
    except OSError as e:
        return f"Cannot read file '{file_path}': {e}"

    parsed = parse_file(file_path, content)
    if parsed is None:
        return f"Unsupported file type or cannot parse '{file_path}'."

    return format_folded_view(parsed)


async def _smart_unfold_impl(file_path: str, symbol_name: str) -> str:
    try:
        content = _read_file(file_path)
    except OSError as e:
        return f"Cannot read file '{file_path}': {e}"

    parsed = parse_file(file_path, content)
    if parsed is None:
        return f"Unsupported file type or cannot parse '{file_path}'."

    symbol = _find_symbol(parsed, symbol_name)
    if symbol is None:
        all_names: list[str] = []
        for sym in parsed.symbols:
            all_names.append(sym.name)
            all_names.extend(c.name for c in sym.children)
        available = ", ".join(all_names) if all_names else "(none)"
        return f"Symbol '{symbol_name}' not found in '{file_path}'. Available: {available}"

    lines = content.splitlines()
    return format_unfold(file_path, symbol, lines)


@mcp.tool()
async def smart_search(
    query: str,
    path: str | None = None,
    max_results: int = 20,
    file_pattern: str | None = None,
) -> str:
    """Search codebase for symbols matching the query using tree-sitter AST parsing.

    Args:
        query: Search query (function name, class name, keyword, etc.)
        path: Directory to search (defaults to current working directory)
        max_results: Maximum number of results to return (default 20)
        file_pattern: Optional glob pattern to filter files (e.g. "*.py")
    """
    return await _smart_search_impl(query, path, max_results, file_pattern)


@mcp.tool()
async def smart_outline(file_path: str) -> str:
    """Get a structural outline of a file — all symbols with signatures, bodies folded.

    Shows functions, classes, methods with their line ranges and docstrings.
    Much more token-efficient than reading the full file.

    Args:
        file_path: Path to the source file to outline
    """
    return await _smart_outline_impl(file_path)


@mcp.tool()
async def smart_unfold(file_path: str, symbol_name: str) -> str:
    """Expand a specific symbol from a file, showing its full source with location.

    Use smart_outline first to discover symbol names, then unfold the ones you need.

    Args:
        file_path: Path to the source file
        symbol_name: Name of the function, class, or method to expand
    """
    return await _smart_unfold_impl(file_path, symbol_name)


if __name__ == "__main__":
    mcp.run(transport="stdio")
