from __future__ import annotations
import sys
from pathlib import Path
if not __package__:
    _DIR = Path(__file__).resolve().parent
    if str(_DIR) not in sys.path:
        sys.path.insert(0, str(_DIR))
if __package__:
    from .doctor import doctor_main
    from .schemas import SCHEMAS
    from .tools import HANDLERS
else:
    from doctor import doctor_main
    from schemas import SCHEMAS
    from tools import HANDLERS
def _setup_cli(parser):
    actions = parser.add_subparsers(dest="ree_action")
    doctor = actions.add_parser("doctor", help="Check local REE requirements")
    doctor.set_defaults(func=doctor_main)
def register(ctx):
    if __package__:
        from .capacity import remember
    else:
        from capacity import remember
    remember(ctx)
    root = Path(__file__).resolve().parent
    for name, schema in SCHEMAS.items():
        ctx.register_tool(
            name=name, toolset="hermes-gensyn-ree", schema=schema,
            handler=HANDLERS[name], description=schema["description"],
        )
    skills = (
        ("ree", "Check a Gensyn REE receipt on this computer. Three stages, not one."),
        ("check-settlement", "Read a Delphi settlement, then check a receipt file the user already has."),
    )
    for name, description in skills:
        ctx.register_skill(name, root / "skills" / name / "SKILL.md", description=description)
    ctx.register_cli_command(
        name="ree", help="Check the local REE plugin", setup_fn=_setup_cli,
        handler_fn=None, description="hermes ree doctor",
    )
