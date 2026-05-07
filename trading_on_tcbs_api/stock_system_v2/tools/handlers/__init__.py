"""Tool handler modules. Each one decorates its functions with `@tool(...)`.

Importing the parent `tools` package eagerly imports every module here,
so the registry is populated by the time any caller looks at `TOOLS`.
"""
