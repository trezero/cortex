"""Tests for the tree-sitter parser and language queries."""

import pytest
from src.smart_explore.parser import CodeSymbol, ParsedFile, parse_file


# ── Python parsing ────────────────────────────────────────────────────────────

PYTHON_SAMPLE = '''\
"""Module docstring."""


def greet(name: str) -> str:
    """Return a greeting."""
    return f"Hello, {name}"


def _private_helper():
    pass


class Greeter:
    """A greeter class."""

    def __init__(self, prefix: str):
        self.prefix = prefix

    def greet(self, name: str) -> str:
        """Greet with prefix."""
        return f"{self.prefix} {name}"

    @staticmethod
    def version() -> str:
        return "1.0"
'''


def test_parse_python_returns_parsed_file():
    result = parse_file("example.py", PYTHON_SAMPLE)
    assert result is not None
    assert isinstance(result, ParsedFile)
    assert result.language == "python"


def test_parse_python_extracts_functions():
    result = parse_file("example.py", PYTHON_SAMPLE)
    names = [s.name for s in result.symbols if s.kind == "function"]
    assert "greet" in names
    assert "_private_helper" in names


def test_parse_python_extracts_class():
    result = parse_file("example.py", PYTHON_SAMPLE)
    classes = [s for s in result.symbols if s.kind == "class"]
    assert any(c.name == "Greeter" for c in classes)


def test_parse_python_methods_nested_inside_class():
    result = parse_file("example.py", PYTHON_SAMPLE)
    greeter = next(s for s in result.symbols if s.name == "Greeter")
    method_names = [c.name for c in greeter.children]
    assert "__init__" in method_names
    assert "greet" in method_names
    assert "version" in method_names


def test_parse_python_line_ranges():
    result = parse_file("example.py", PYTHON_SAMPLE)
    greet_fn = next(s for s in result.symbols if s.name == "greet" and s.kind == "function")
    assert greet_fn.line_start >= 1
    assert greet_fn.line_end >= greet_fn.line_start


def test_parse_python_docstring_extraction():
    result = parse_file("example.py", PYTHON_SAMPLE)
    greet_fn = next(s for s in result.symbols if s.name == "greet" and s.kind == "function")
    assert greet_fn.docstring is not None
    assert "greeting" in greet_fn.docstring.lower()


def test_parse_python_line_count():
    result = parse_file("example.py", PYTHON_SAMPLE)
    expected = len(PYTHON_SAMPLE.splitlines())
    assert result.line_count == expected


# ── TypeScript parsing ────────────────────────────────────────────────────────

TYPESCRIPT_SAMPLE = '''\
export interface User {
  id: string;
  name: string;
}

export function createUser(name: string): User {
  return { id: "1", name };
}

export class UserService {
  private users: User[] = [];

  add(user: User): void {
    this.users.push(user);
  }

  find(id: string): User | undefined {
    return this.users.find(u => u.id === id);
  }
}
'''


def test_parse_typescript_returns_parsed_file():
    result = parse_file("service.ts", TYPESCRIPT_SAMPLE)
    assert result is not None
    assert result.language == "typescript"


def test_parse_typescript_extracts_interface():
    result = parse_file("service.ts", TYPESCRIPT_SAMPLE)
    names = [s.name for s in result.symbols]
    assert "User" in names


def test_parse_typescript_extracts_function():
    result = parse_file("service.ts", TYPESCRIPT_SAMPLE)
    fns = [s for s in result.symbols if s.kind == "function"]
    assert any(f.name == "createUser" for f in fns)


def test_parse_typescript_extracts_class():
    result = parse_file("service.ts", TYPESCRIPT_SAMPLE)
    classes = [s for s in result.symbols if s.kind == "class"]
    assert any(c.name == "UserService" for c in classes)


# ── Unknown language ──────────────────────────────────────────────────────────


def test_parse_unknown_language_returns_none():
    result = parse_file("data.csv", "a,b,c\n1,2,3")
    assert result is None


def test_parse_binary_extension_returns_none():
    result = parse_file("image.png", "binary data")
    assert result is None


# ── Edge cases ────────────────────────────────────────────────────────────────


def test_parse_empty_python_file():
    result = parse_file("empty.py", "")
    assert result is not None
    assert result.symbols == []


def test_parse_python_tsx_extension():
    tsx_content = "export const App = () => <div>Hello</div>;\n"
    result = parse_file("App.tsx", tsx_content)
    assert result is not None
    assert result.language == "tsx"
