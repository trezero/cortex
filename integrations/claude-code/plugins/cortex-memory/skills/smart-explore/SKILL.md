---
name: smart-explore
description: Token-efficient codebase exploration using tree-sitter AST tools. Use instead of reading full files when exploring codebases, finding functions, or understanding code structure. Trigger when navigating unfamiliar codebases or needing to locate specific symbols efficiently.
---

# Smart Explore

Token-efficient, AST-powered codebase exploration. Use these tools instead of reading full files — they give you structure without the noise.

## The 3-Layer Workflow

### Layer 1: Search — Find what you're looking for
```
smart_search(query="authenticate user", path="src/")
```
Returns ranked symbol matches with signatures and file locations. Use when you know roughly what to look for but not where it lives.

### Layer 2: Outline — Understand a file's structure
```
smart_outline(file_path="src/auth/auth_service.py")
```
Returns all symbols (functions, classes, methods) with signatures, bodies folded. ~50 tokens for a 500-line file vs ~2,000 tokens for full read.

### Layer 3: Unfold — Read exactly what you need
```
smart_unfold(file_path="src/auth/auth_service.py", symbol_name="authenticate")
```
Returns full source of one symbol with location markers. Use after outline to expand only the relevant parts.

## Token Economics

| Tool | Typical tokens | vs full Read |
|------|---------------|--------------|
| smart_search (20 results) | ~300 | 90% savings |
| smart_outline (50-line file) | ~80 | 70% savings |
| smart_unfold (one function) | ~100 | 85% savings |

## When to Use Standard Tools Instead

- Config files, JSON, YAML, Markdown → use Read
- Searching for string literals, comments, imports → use Grep
- Reading a file you're about to edit entirely → use Read
- Files < 50 lines → Read is fine

## Supported Languages

Python, JavaScript, TypeScript, TSX, Go, Rust, Java, Ruby, C, C++
