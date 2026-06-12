"""Tree-sitter query patterns and language configuration for smart-explore."""

# Maps file extensions to tree-sitter language names
EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
}

# Tree-sitter S-expression queries per language.
# Captures:
#   @name    — the identifier node of the definition
#   @def     — the full definition node (used for line ranges)
LANGUAGE_QUERIES: dict[str, str] = {
    "python": """
        (function_definition
            name: (identifier) @name) @def

        (class_definition
            name: (identifier) @name) @def
    """,
    "javascript": """
        (function_declaration
            name: (identifier) @name) @def

        (class_declaration
            name: (identifier) @name) @def

        (lexical_declaration
            (variable_declarator
                name: (identifier) @name
                value: [(arrow_function) (function_expression)])) @def

        (variable_declaration
            (variable_declarator
                name: (identifier) @name
                value: [(arrow_function) (function_expression)])) @def

        (method_definition
            name: (property_identifier) @name) @def
    """,
    "typescript": """
        (function_declaration
            name: (identifier) @name) @def

        (class_declaration
            name: (type_identifier) @name) @def

        (interface_declaration
            name: (type_identifier) @name) @def

        (type_alias_declaration
            name: (type_identifier) @name) @def

        (lexical_declaration
            (variable_declarator
                name: (identifier) @name
                value: [(arrow_function) (function_expression)])) @def

        (method_definition
            name: (property_identifier) @name) @def
    """,
    "tsx": """
        (function_declaration
            name: (identifier) @name) @def

        (class_declaration
            name: (type_identifier) @name) @def

        (interface_declaration
            name: (type_identifier) @name) @def

        (type_alias_declaration
            name: (type_identifier) @name) @def

        (lexical_declaration
            (variable_declarator
                name: (identifier) @name
                value: [(arrow_function) (function_expression) (jsx_element) (jsx_self_closing_element)])) @def

        (method_definition
            name: (property_identifier) @name) @def
    """,
    "go": """
        (function_declaration
            name: (identifier) @name) @def

        (method_declaration
            name: (field_identifier) @name) @def

        (type_declaration
            (type_spec name: (type_identifier) @name)) @def
    """,
    "rust": """
        (function_item
            name: (identifier) @name) @def

        (struct_item
            name: (type_identifier) @name) @def

        (enum_item
            name: (type_identifier) @name) @def

        (impl_item
            type: (type_identifier) @name) @def

        (trait_item
            name: (type_identifier) @name) @def
    """,
    "java": """
        (method_declaration
            name: (identifier) @name) @def

        (class_declaration
            name: (identifier) @name) @def

        (interface_declaration
            name: (identifier) @name) @def

        (enum_declaration
            name: (identifier) @name) @def
    """,
    "ruby": """
        (method
            name: (identifier) @name) @def

        (singleton_method
            name: (identifier) @name) @def

        (class
            name: [(constant) (scope_resolution)] @name) @def

        (module
            name: [(constant) (scope_resolution)] @name) @def
    """,
    "c": """
        (function_definition
            declarator: (function_declarator
                declarator: (identifier) @name)) @def

        (struct_specifier
            name: (type_identifier) @name) @def
    """,
    "cpp": """
        (function_definition
            declarator: (function_declarator
                declarator: [(identifier) (qualified_identifier)] @name)) @def

        (class_specifier
            name: (type_identifier) @name) @def

        (struct_specifier
            name: (type_identifier) @name) @def
    """,
}

# Node types that indicate a class/struct/interface definition
CLASS_KINDS = {
    "class_definition",        # Python
    "class_declaration",       # JS/TS/Java
    "interface_declaration",   # TS/Java
    "struct_item",             # Rust
    "enum_item",               # Rust
    "impl_item",               # Rust
    "trait_item",              # Rust
    "class_specifier",         # C++
    "struct_specifier",        # C/C++
    "type_declaration",        # Go
    "class",                   # Ruby
    "module",                  # Ruby
    "type_alias_declaration",  # TS
    "enum_declaration",        # Java
}
