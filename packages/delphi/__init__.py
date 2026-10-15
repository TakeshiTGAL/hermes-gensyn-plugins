"""Delphi 0.2-live: seven read-only tools for Hermes Agent."""
from __future__ import annotations
from pathlib import Path
if __package__:
    from .doctor import doctor_main
    from .hooks import on_transform_tool_result
    from .schemas import SCHEMAS
    from .settings import bind_config
    from .tools import HANDLERS
else:
    from doctor import doctor_main
    from hooks import on_transform_tool_result
    from schemas import SCHEMAS
    from settings import bind_config
    from tools import HANDLERS
def _setup_cli(parser):
    actions = parser.add_subparsers(dest="gensyn_action")
    doctor = actions.add_parser("doctor", help="Check local Delphi requirements")
    doctor.set_defaults(func=doctor_main)
def register(ctx):
    getter = getattr(ctx, "get_config", None)
    bind_config(getter if callable(getter) else None)
    for name, schema in SCHEMAS.items():
        ctx.register_tool( name=name, toolset="hermes-gensyn-delphi", schema=schema, handler=HANDLERS[name],
            description=schema["description"], )
    ctx.register_hook("transform_tool_result", on_transform_tool_result)
    skill = Path(__file__).resolve().parent / "skills" / "delphi" / "SKILL.md"
    ctx.register_skill( "delphi",
        skill, description="Read Delphi markets and compute an arithmetic edge; never trade.", )
    ctx.register_cli_command( name="gensyn", help="Check the local Delphi plugin", setup_fn=_setup_cli,
        handler_fn=None, description="hermes gensyn doctor", )
