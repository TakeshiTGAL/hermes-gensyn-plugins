from __future__ import annotations
if __package__:
    from .service import infer, validate_receipt, verify_receipt
else:
    from service import infer, validate_receipt, verify_receipt
def _call(function, args):
    return function(args if isinstance(args, dict) else {})
def _ids(kwargs):
    return {
        "session_id": str(kwargs.get("session_id") or ""),
        "task_id": str(kwargs.get("task_id") or ""),
    }
def ree_validate_receipt(args, **_kwargs):
    return _call(validate_receipt, args)
def ree_verify_receipt(args, **kwargs):
    return verify_receipt(args if isinstance(args, dict) else {}, **_ids(kwargs))
def ree_infer(args, **kwargs):
    return infer(args if isinstance(args, dict) else {}, **_ids(kwargs))
HANDLERS = {
    "ree_validate_receipt": ree_validate_receipt,
    "ree_verify_receipt": ree_verify_receipt,
    "ree_infer": ree_infer,
}
