from __future__ import annotations
if __package__:
    from .contract import MODELS
else:
    from contract import MODELS
DESCRIPTIONS = {
    "ree_validate_receipt": (
        "Returns hash checks. No key. Read-only. It does not re-execute. consistent is not a text check."
    ),
    "ree_verify_receipt": (
        "Returns a re-execution comparison. Needs approval. It checks the text fields after the hashes."
    ),
    "ree_infer": (
        "Returns one new receipt. Needs approval. Prompt rejects newline, CR, NUL, and a leading hyphen. "
        "model is facebook/opt-125m, Qwen/Qwen2.5-0.5B, or Qwen/Qwen3-0.6B."
    ),
}
def _schema(name):
    infer = name == "ree_infer"
    properties = {
        "model": {"type": "string", "enum": list(MODELS)},
        "prompt": {"type": "string", "minLength": 1, "maxLength": 4000},
        "max_new_tokens": {"type": "integer", "minimum": 1, "maximum": 256},
    } if infer else {"receipt_path": {"type": "string", "minLength": 1, "maxLength": 4096}}
    required = ["model", "prompt", "max_new_tokens"] if infer else ["receipt_path"]
    return {
        "name": name, "description": DESCRIPTIONS[name],
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": properties, "required": required,
        },
    }
SCHEMAS = {name: _schema(name) for name in DESCRIPTIONS}
