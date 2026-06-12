"""Tree-sitter based code parser for smart-explore.

Extracts symbols (functions, classes, methods) from source files
using tree-sitter AST parsing with language-specific queries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .queries import CLASS_KINDS, EXTENSION_TO_LANGUAGE, LANGUAGE_QUERIES


@dataclass
class CodeSymbol:
    """A code symbol extracted from a source file."""

    name: str
    kind: str  # "function", "class", "method", "interface", "type", etc.
    line_start: int  # 1-based
    line_end: int  # 1-based, inclusive
    parent: str | None = None
    signature: str = ""
    docstring: str | None = None
    exported: bool = False
    children: list[CodeSymbol] = field(default_factory=list)


@dataclass
class ParsedFile:
    """Result of parsing a source file."""

    path: str
    language: str
    symbols: list[CodeSymbol]
    imports: list[str]
    line_count: int


def _get_language_name(file_path: str) -> str | None:
    """Detect language from file extension."""
    suffix = Path(file_path).suffix.lower()
    return EXTENSION_TO_LANGUAGE.get(suffix)


def extract_signature(lines: list[str], start_line: int) -> str:
    """Get the declaration signature (first 1-2 lines of definition, 0-based start_line)."""
    if start_line >= len(lines):
        return ""
    first = lines[start_line].rstrip()
    # If the line ends with a colon (Python) or open brace/arrow, grab 1 line
    return first


def extract_docstring(lines: list[str], symbol_start: int, language: str) -> str | None:
    """Extract the docstring/comment immediately following a definition.

    For Python: looks for triple-quoted string on the line after the def.
    For other languages: looks for // or /* comments preceding the symbol.
    """
    if language == "python":
        # Look for triple-quoted docstring starting on the next non-empty body line
        body_start = symbol_start + 1  # line after the def line (0-based)
        # Skip blank lines
        while body_start < len(lines) and not lines[body_start].strip():
            body_start += 1
        if body_start >= len(lines):
            return None
        stripped = lines[body_start].strip()
        if stripped.startswith('"""') or stripped.startswith("'''"):
            quote = '"""' if stripped.startswith('"""') else "'''"
            # Single-line docstring
            if stripped.count(quote) >= 2 and len(stripped) > 3:
                return stripped.strip(quote).strip()
            # Multi-line: collect until closing quote
            doc_lines = [stripped.lstrip(quote)]
            for i in range(body_start + 1, min(body_start + 20, len(lines))):
                line = lines[i].strip()
                if quote in line:
                    doc_lines.append(line.rstrip(quote).strip())
                    break
                doc_lines.append(line)
            return " ".join(l for l in doc_lines if l).strip()
        return None
    else:
        # Look for // or /* comment on the line immediately before the symbol
        check = symbol_start - 1
        if check < 0:
            return None
        line = lines[check].strip()
        if line.startswith("//"):
            return line.lstrip("/ ").strip()
        if line.startswith("*") or line.startswith("/*"):
            return line.lstrip("/* ").strip()
        return None


def detect_exported(node_text: str, language: str) -> bool:
    """Detect if a symbol is exported based on language conventions."""
    if language in ("javascript", "typescript", "tsx"):
        return node_text.lstrip().startswith("export")
    if language == "python":
        # Python convention: not starting with _ means public
        return True
    if language == "go":
        # Go: uppercase first letter = exported
        return bool(re.match(r"[A-Z]", node_text.strip()))
    return False


def _node_kind(node_type: str) -> str:
    """Map tree-sitter node type to human-readable kind."""
    if node_type in CLASS_KINDS:
        return "class"
    if "function" in node_type or "method" in node_type:
        return "function"
    if "interface" in node_type:
        return "interface"
    if "type" in node_type:
        return "type"
    return "symbol"


def nest_symbols(flat: list[CodeSymbol]) -> list[CodeSymbol]:
    """Nest method symbols inside their parent class by line range.

    Takes a flat list of symbols sorted by line_start. Methods that fall
    within a class's line range become children of that class.
    """
    # Sort by line_start for deterministic ordering
    sorted_symbols = sorted(flat, key=lambda s: s.line_start)

    top_level: list[CodeSymbol] = []
    classes: list[CodeSymbol] = []

    for sym in sorted_symbols:
        # Find the innermost class that contains this symbol's line range
        parent_class = None
        for cls in reversed(classes):
            if cls.line_start <= sym.line_start and sym.line_end <= cls.line_end:
                parent_class = cls
                break

        if parent_class is not None and sym is not parent_class:
            sym.parent = parent_class.name
            # Convert function→method when nested in a class
            if sym.kind == "function":
                sym.kind = "method"
            parent_class.children.append(sym)
        else:
            top_level.append(sym)
            if sym.kind == "class":
                classes.append(sym)

    return top_level


def parse_file(file_path: str, content: str) -> ParsedFile | None:
    """Parse a source file and extract its symbols.

    Args:
        file_path: Path to the file (used for language detection).
        content: Source code content as a string.

    Returns:
        ParsedFile with extracted symbols, or None if language unsupported.
    """
    language = _get_language_name(file_path)
    if language is None:
        return None

    query_str = LANGUAGE_QUERIES.get(language)
    if query_str is None:
        return None

    lines = content.splitlines()
    line_count = len(lines)

    try:
        from tree_sitter import Parser, Query, QueryCursor
        from tree_sitter_language_pack import get_language as get_ts_language

        ts_language = get_ts_language(language)
        parser = Parser(ts_language)
        tree = parser.parse(content.encode("utf-8"))

        query = Query(ts_language, query_str)
        cursor = QueryCursor(query)
        matches = list(cursor.matches(tree.root_node))

    except Exception:
        # Graceful degradation: if tree-sitter fails, return empty file
        return ParsedFile(
            path=file_path,
            language=language,
            symbols=[],
            imports=[],
            line_count=line_count,
        )

    flat_symbols: list[CodeSymbol] = []
    seen: set[tuple[str, int]] = set()  # (name, line_start) dedup

    for _pattern_index, capture_dict in matches:
        name_nodes = capture_dict.get("name", [])
        def_nodes = capture_dict.get("def", [])

        if not name_nodes or not def_nodes:
            continue

        name_node = name_nodes[0] if isinstance(name_nodes, list) else name_nodes
        def_node = def_nodes[0] if isinstance(def_nodes, list) else def_nodes

        name = name_node.text.decode("utf-8") if name_node.text else ""
        if not name:
            continue

        line_start = def_node.start_point[0] + 1  # 0→1 based
        line_end = def_node.end_point[0] + 1

        key = (name, line_start)
        if key in seen:
            continue
        seen.add(key)

        kind = _node_kind(def_node.type)
        sig = extract_signature(lines, def_node.start_point[0])
        doc = extract_docstring(lines, def_node.start_point[0], language)
        exported = detect_exported(sig, language)

        flat_symbols.append(CodeSymbol(
            name=name,
            kind=kind,
            line_start=line_start,
            line_end=line_end,
            signature=sig,
            docstring=doc,
            exported=exported,
        ))

    nested = nest_symbols(flat_symbols)

    return ParsedFile(
        path=file_path,
        language=language,
        symbols=nested,
        imports=[],
        line_count=line_count,
    )
