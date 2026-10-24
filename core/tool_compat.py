"""Strict compatibility parser for models that emit a tool call as text."""

import ast


def parse_text_tool_call(text: str, allowed_names) -> tuple | None:
    """Accept only one complete ``known_tool(literal, ...)`` expression."""
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        tree = ast.parse(text.strip(), mode="eval")
    except SyntaxError:
        return None
    call = tree.body
    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
        return None
    name = call.func.id
    if name not in allowed_names or any(kw.arg is None for kw in call.keywords):
        return None

    def literal(node):
        # A few compatible models omit quotes around a simple app name.
        if isinstance(node, ast.Name):
            return node.id
        return ast.literal_eval(node)

    try:
        args = [literal(node) for node in call.args]
        kwargs = {kw.arg: literal(kw.value) for kw in call.keywords}
    except (ValueError, TypeError):
        return None
    return name, args, kwargs
