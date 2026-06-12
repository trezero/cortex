# Cortex Memory Plugin

This plugin provides smart code exploration and session memory for Claude Code.

## Code Exploration Tools (cortex-memory MCP server)

Three token-efficient tools for navigating large codebases:

- **smart_search** — Search for functions, classes, or symbols across a codebase using tree-sitter AST parsing. Returns ranked matches with signatures and location info. Use instead of grep when looking for symbol definitions.
- **smart_outline** — Get a structural overview of a single file: all symbols with signatures, bodies folded. Much more token-efficient than reading the full file. Use before deciding which symbols to unfold.
- **smart_unfold** — Expand a specific symbol to its full source with location markers. Use after smart_outline to read only the parts you need.

### When to use smart tools vs standard tools
- `smart_search` instead of Grep when looking for function/class definitions
- `smart_outline` instead of Read when you need a file's structure, not full content
- `smart_unfold` instead of Read for a single function or class body
- Use standard Read/Grep for config files, logs, plain text files

## Session Memory

Observations are automatically captured during each session via hooks:
- **SessionStart**: Loads recent sessions, active tasks, and knowledge sources from Cortex into context
- **PostToolUse**: Appends lightweight observations to a local buffer (fast, no network calls)
- **Stop**: Flushes the session buffer to Cortex for long-term storage

If Cortex is not configured, smart_search/smart_outline/smart_unfold still work — session memory is simply skipped.
