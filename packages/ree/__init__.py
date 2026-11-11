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
def _load_gate():
    if __package__:
        from . import gate
        from .service import approval_ready
    else:
        import gate
        from service import approval_ready
    return gate, approval_ready
def _on_pre_tool_call(tool_name="", args=None, **kwargs):
    if tool_name not in ("ree_verify_receipt", "ree_infer"):
        return None
    try:
        gate, approval_ready = _load_gate()
        session_id = str(kwargs.get("session_id") or "")
        task_id = str(kwargs.get("task_id") or "")
        gate.clear_room(session_id, task_id)
        reason = gate.command_block_reason()
        if reason:
            return {"action": "block", "message": reason}
        ready = approval_ready(tool_name, args if isinstance(args, dict) else {})
        if not ready:
            return None
        plan = ready["plan"]
        return gate.issue(
            ready["kind"], ready["model"], ready["max_new_tokens"],
            machine=plan["machine"], note=plan["note"], cpu_only=plan["cpu_only"],
            session_id=session_id, task_id=task_id, receipt_hash=ready["receipt_hash"],
        )
    except Exception:
        return {
            "action": "block",
            "message": "BLOCKED: approval failed closed, so the call was refused.",
        }
def _on_approval_response(**kwargs):
    try:
        gate, _ready = _load_gate()
        gate.note_response(
            pattern_key=kwargs.get("pattern_key") or "",
            pattern_keys=kwargs.get("pattern_keys"),
            choice=kwargs.get("choice") if isinstance(kwargs.get("choice"), str) else "",
            decided_by=kwargs.get("decided_by"),
        )
    except Exception:
        return None
def register(ctx):
    if __package__:
        from .capacity import remember
        from .gate import bind_context
    else:
        from capacity import remember
        from gate import bind_context
    bind_context(ctx)
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
    ctx.register_hook("pre_tool_call", _on_pre_tool_call)
    ctx.register_hook("post_approval_response", _on_approval_response)
    ctx.register_cli_command(
        name="ree", help="Check the local REE plugin", setup_fn=_setup_cli,
        handler_fn=None, description="hermes ree doctor",
    )
