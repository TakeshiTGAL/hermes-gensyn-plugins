from __future__ import annotations
if __package__:
    from .service import infer, validate_receipt, verify_receipt
else:
    from service import infer, validate_receipt, verify_receipt
def _call(function, args):
    return function(args if isinstance(args, dict) else {})
def ree_validate_receipt(args, **_kwargs):
    return _call(validate_receipt, args)
def ree_verify_receipt(args, **_kwargs):
    return _call(verify_receipt, args)
def ree_infer(args, **_kwargs):
    return _call(infer, args)
HANDLERS = {
    "ree_validate_receipt": ree_validate_receipt,
    "ree_verify_receipt": ree_verify_receipt,
    "ree_infer": ree_infer,
}
