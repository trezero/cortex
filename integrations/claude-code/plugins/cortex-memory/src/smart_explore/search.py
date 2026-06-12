"""Search and ranking for smart-explore.

Provides directory walking, symbol scoring, and result formatting
for tree-sitter based codebase search.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .parser import CodeSymbol, ParsedFile, parse_file
from .queries import EXTENSION_TO_LANGUAGE

# Directories to skip when walking the codebase
_IGNORED_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    "dist",
    "vendor",
    ".venv",
    "venv",
    "build",
    ".next",
    "target",
    "out",
    ".cache",
}

_MAX_FILE_SIZE = 512 * 1024  # 512 KB


@dataclass
class SearchResult:
    """Result of a codebase search."""

    matching_symbols: list[tuple[CodeSymbol, int, str]]  # (symbol, score, reason)
    folded_files: list[ParsedFile]
    stats: dict[str, int]
    token_estimate: int


def walk_directory(root: str, max_depth: int = 20, file_pattern: str | None = None) -> list[str]:
    """Discover code files under root, skipping ignored directories and large files.

    Returns absolute paths to parseable code files.
    """
    found: list[str] = []
    root_depth = root.rstrip(os.sep).count(os.sep)

    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        # Enforce max depth
        current_depth = dirpath.count(os.sep) - root_depth
        if current_depth >= max_depth:
            dirnames.clear()
            continue

        # Prune ignored directories in-place so os.walk skips them
        dirnames[:] = [d for d in dirnames if d not in _IGNORED_DIRS and not d.startswith(".")]

        for fname in filenames:
            fpath = os.path.join(dirpath, fname)

            # Extension filter
            suffix = os.path.splitext(fname)[1].lower()
            if suffix not in EXTENSION_TO_LANGUAGE:
                continue

            # Optional glob pattern filter
            if file_pattern and not _fnmatch(fname, file_pattern):
                continue

            # Size limit
            try:
                if os.path.getsize(fpath) > _MAX_FILE_SIZE:
                    continue
            except OSError:
                continue

            found.append(fpath)

    return found


def _fnmatch(name: str, pattern: str) -> bool:
    """Simple filename matching supporting * wildcards."""
    import fnmatch
    return fnmatch.fnmatch(name, pattern)


def match_score(text: str, query_parts: list[str]) -> int:
    """Score how well text matches the query parts.

    Scoring per query part (case-insensitive):
    - Exact match of the full text: +10
    - Substring match of the part in the text: +5
    - Fuzzy token match: any underscore-delimited token from the part
      (minimum 3 chars) appears in the text: +1

    Returns total score across all query parts.
    """
    if not query_parts or not text:
        return 0

    text_lower = text.lower()
    total = 0

    for part in query_parts:
        part_lower = part.lower()
        if not part_lower:
            continue

        if text_lower == part_lower:
            total += 10
        elif part_lower in text_lower:
            total += 5
        else:
            # Fuzzy: check if any meaningful token (>= 3 chars) from the
            # query part appears as a substring in the text
            tokens = [t for t in part_lower.replace("-", "_").split("_") if len(t) >= 3]
            if tokens and any(tok in text_lower for tok in tokens):
                total += 1

    return total


def rank_symbols(symbols: list[CodeSymbol], query: str) -> list[tuple[CodeSymbol, int, str]]:
    """Score and rank symbols by relevance to query.

    Scoring weights:
    - Name match: 3x multiplier
    - Signature match: 2x multiplier
    - Docstring match: 1x multiplier

    Returns list of (symbol, total_score, match_reason) sorted by score descending,
    excluding symbols with zero score.
    """
    query_parts = query.lower().split()
    results: list[tuple[CodeSymbol, int, str]] = []

    for sym in symbols:
        name_score = match_score(sym.name, query_parts) * 3
        sig_score = match_score(sym.signature, query_parts) * 2
        doc_score = match_score(sym.docstring or "", query_parts) * 1

        total = name_score + sig_score + doc_score
        if total == 0:
            continue

        # Build a human-readable reason
        reasons: list[str] = []
        if name_score:
            reasons.append(f"name:{_score_label(sym.name, query_parts)}")
        if sig_score:
            reasons.append(f"signature:{_score_label(sym.signature, query_parts)}")
        if doc_score:
            reasons.append(f"docstring:{_score_label(sym.docstring or '', query_parts)}")
        reason = ", ".join(reasons)

        results.append((sym, total, reason))

        # Also score children (methods inside classes)
        for child in sym.children:
            child_name = match_score(child.name, query_parts) * 3
            child_sig = match_score(child.signature, query_parts) * 2
            child_doc = match_score(child.docstring or "", query_parts) * 1
            child_total = child_name + child_sig + child_doc
            if child_total > 0:
                child_reasons: list[str] = []
                if child_name:
                    child_reasons.append(f"name:{_score_label(child.name, query_parts)}")
                if child_sig:
                    child_reasons.append(f"signature:{_score_label(child.signature, query_parts)}")
                results.append((child, child_total, ", ".join(child_reasons)))

    results.sort(key=lambda t: t[1], reverse=True)
    return results


def _score_label(text: str, query_parts: list[str]) -> str:
    """Return 'exact', 'substring', or 'fuzzy' label for the best match."""
    text_lower = text.lower()
    for part in query_parts:
        p = part.lower()
        if text_lower == p:
            return "exact"
        if p in text_lower:
            return "substring"
    return "fuzzy"


def search_codebase(
    root: str,
    query: str,
    max_results: int = 20,
    file_pattern: str | None = None,
) -> SearchResult:
    """Full search pipeline: walk → parse → rank → return results.

    Args:
        root: Directory to search.
        query: Search query string.
        max_results: Maximum number of matching symbols to return.
        file_pattern: Optional glob pattern to filter files (e.g., "*.py").

    Returns:
        SearchResult with ranked matching symbols and statistics.
    """
    code_files = walk_directory(root, file_pattern=file_pattern)
    files_scanned = len(code_files)
    files_parsed = 0
    symbols_found = 0
    all_ranked: list[tuple[CodeSymbol, int, str]] = []
    folded_files: list[ParsedFile] = []

    for fpath in code_files:
        try:
            content = Path(fpath).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        parsed = parse_file(fpath, content)
        if parsed is None:
            continue

        files_parsed += 1
        symbols_found += len(parsed.symbols)
        ranked = rank_symbols(parsed.symbols, query)
        all_ranked.extend(ranked)
        if ranked:
            folded_files.append(parsed)

    # Sort all results globally and cap
    all_ranked.sort(key=lambda t: t[1], reverse=True)
    top = all_ranked[:max_results]

    # Token estimate: rough heuristic (~4 chars per token)
    estimated_chars = sum(
        len(sym.signature) + len(sym.docstring or "") + 50
        for sym, _, _ in top
    )
    token_estimate = estimated_chars // 4

    return SearchResult(
        matching_symbols=top,
        folded_files=folded_files,
        stats={
            "files_scanned": files_scanned,
            "files_parsed": files_parsed,
            "symbols_found": symbols_found,
        },
        token_estimate=token_estimate,
    )


def format_folded_view(parsed_file: ParsedFile) -> str:
    """Render a compact structural outline of a file.

    Shows all symbols with their signatures and line ranges,
    with methods indented under their parent class.
    """
    lines: list[str] = [f"# {parsed_file.path}  ({parsed_file.line_count} lines, {parsed_file.language})"]

    def _render(sym: CodeSymbol, indent: int = 0) -> None:
        prefix = "  " * indent
        kind_tag = f"[{sym.kind}]"
        loc = f"L{sym.line_start}-{sym.line_end}"
        sig = sym.signature.strip() if sym.signature else sym.name
        line = f"{prefix}{kind_tag} {sig}  {loc}"
        lines.append(line)
        if sym.docstring:
            lines.append(f"{prefix}  # {sym.docstring[:80]}")
        for child in sym.children:
            _render(child, indent + 1)

    for sym in parsed_file.symbols:
        _render(sym)

    return "\n".join(lines)


def format_search_results(result: SearchResult) -> str:
    """Render search results as human-readable text.

    Includes matched symbols with location and relevance, plus scan statistics.
    """
    parts: list[str] = []

    stats = result.stats
    header = (
        f"Search results — {len(result.matching_symbols)} match(es) | "
        f"{stats.get('files_scanned', 0)} files scanned, "
        f"{stats.get('files_parsed', 0)} parsed, "
        f"{stats.get('symbols_found', 0)} symbols found"
    )
    parts.append(header)
    parts.append("")

    if not result.matching_symbols:
        parts.append("No results found.")
        return "\n".join(parts)

    # Group by file path for readability using ParsedFile.path as context
    file_of: dict[str, str] = {}
    for pf in result.folded_files:
        for sym in pf.symbols:
            file_of[id(sym)] = pf.path
            for child in sym.children:
                file_of[id(child)] = pf.path

    for sym, score, reason in result.matching_symbols:
        fpath = file_of.get(id(sym), "")
        loc = f"L{sym.line_start}"
        file_info = f"{fpath}:{loc}" if fpath else loc
        sig = sym.signature.strip() if sym.signature else sym.name
        parts.append(f"  [{sym.kind}] {sig}  ({file_info}, score={score}, {reason})")
        if sym.docstring:
            parts.append(f"    # {sym.docstring[:100]}")

    parts.append("")
    parts.append(f"~{result.token_estimate} tokens estimated")
    return "\n".join(parts)


def format_unfold(file_path: str, symbol: CodeSymbol, lines: list[str]) -> str:
    """Render the full source of a symbol with location header.

    Extracts lines from line_start to line_end (1-based, inclusive).
    """
    start = symbol.line_start - 1  # convert to 0-based
    end = symbol.line_end  # exclusive for slicing
    source_lines = lines[start:end]

    header = f"# {file_path}  {symbol.kind} '{symbol.name}'  L{symbol.line_start}-{symbol.line_end}"
    return header + "\n" + "\n".join(source_lines)


