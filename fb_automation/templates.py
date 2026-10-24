from __future__ import annotations

from jinja2.sandbox import ImmutableSandboxedEnvironment

_environment = ImmutableSandboxedEnvironment()
_environment.globals.clear()


def render_message(template_str: str, contact: dict[str, str]) -> str:
    """Render a Jinja2 template string with contact fields.

    Example template: "Hey {{first_name}}, just checking in about {{custom_field}}!"
    Contact dict keys become template variables.
    """
    tpl = _environment.from_string(template_str)
    return tpl.render(**contact)
