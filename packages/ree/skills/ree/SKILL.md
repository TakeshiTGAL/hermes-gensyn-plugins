---
name: ree
description: Check a Gensyn REE receipt on this computer. Three stages, not one.
---

# REE 0.1

REE is a Gensyn product. This plugin only runs the official image. It does
not redistribute or reimplement it.

## When a receipt arrives

1. Call `ree_validate_receipt` with `receipt_path` first. This stage does not
   re-execute the model and does not ask for approval. It runs on this
   machine for any model size. It does not load the weights.
2. Say which hash lines passed or failed. Do not quote `text_output` from
   this result. This stage does not return it, and it does not stand behind
   `text_output`, `finish_reason`, `token_count`, `model.name`,
   `ree_version`, `execution.device_type`, `execution.device_name`, or
   `input.parameters.torch_dtype`.
3. A `consistent` result includes `next`. Propose `ree_verify_receipt`.
   It has `needs_approval`. It checks re-execution and the text fields.
   Do not call it in the same turn. Call it only after the user agrees.
4. `ree_verify_receipt` asks for approval, re-executes on CPU, and may
   download weights. A model outside the three small names can be gigabytes,
   may not fit memory, and CPU-only can take a long time. Then compare the
   readable fields with the new receipt.
5. Use `ree_infer` only when the user wants a new generation, not when they
   handed you an existing receipt. `prompt` is text from 1 to 4000 characters
   without newline, CR, NUL, or a leading hyphen. `model` is
   `facebook/opt-125m`, `Qwen/Qwen2.5-0.5B`, or `Qwen/Qwen3-0.6B`. It also
   asks for approval.
6. `approval_denied` means approval was not granted. `approval_unavailable`
   means approval was not obtained (could not ask, or there was no answer).
   Both have `retryable` false. Do not retry. Validate runs before the
   question. An inconsistent receipt does not ask.

Do not call a hash PASS "verified", "genuine", or "authentic".
Quote `level` as returned.

## What the levels mean

| `level` | Meaning |
| --- | --- |
| `consistent` | Official validate returned each of the four hash lines once, all PASS, and the exit code was 0. The text is not in this result. |
| `inconsistent` | Official validate returned each of the four hash lines once, at least one FAIL, and the exit code was 1. |
| `reexecuted` | Token hashes matched, the exit code was 0, and exactly one new receipt was written. `text_output` was not on both receipts, so `text_compared` is false and `text_skip_reason` says which side. This is not a text match. |
| `reexecuted_and_text_match` | The exit code was 0, exactly one new receipt, every compared hash matched, and every compared readable field matched. `text_output` counts only when `text_compared` is true. |
| `text_mismatch` | The exit code was 0, exactly one new receipt, every compared hash matched, and a compared readable field differs. Token hashes are the verdict. |
| `reexecution_mismatch` | Exactly one new receipt and a compared hash differs. The exit code may be 0 or not. |
| `inferred` | The exit code was 0 and exactly one new receipt was written. It was not compared with an older receipt. |

There is no `level` for these:

| `error_type` | Meaning |
| --- | --- |
| `reexecution_incomplete` | The exit code was not 0 and there is no new receipt. Hashes were not compared. |
| `validate_incomplete` | The four hash lines and the exit code do not agree. |
| `internal` | Any other combination, or an exact prefixed official claim disagrees with the receipt files. |
| `docker_unavailable` | The container did not start. The result says nothing about the receipt. |
| `image_missing` | The container did not start. The result says nothing about the receipt. |
| `container_not_started` | The container did not start. The result says nothing about the receipt. |
| `unsupported_receipt_version` | The receipt version is not 2.0.0. Nothing was checked. |
| `insufficient_memory` | The weights are larger than Docker memory. Hash validation still runs here. |
| `context_mount_unavailable` | The Docker context cannot mount the receipt and work files. |
| `killed` | The container exited 137. That can be out of memory. It is not a time limit. |

Compared hashes: `output.tokens_hash`, `input.prompt_hash`, `input.tools_hash`, `input.parameters_hash`, `hashes.receipt_hash`, `model.config_hash`, `model.commit_hash`.
Readable fields: `output.text_output` (only when both receipts include it), `output.finish_reason`, `output.token_count`, `model.name`, `input.prompt`. `text_compared` is false when `text_output` is absent.
`reexecuted_and_text_match` includes `not_compared` for `ree_version` and the execution fields. A larger model may not finish on this CPU. That result is not a failed hash check.

`receipt_text` and each `differences` row, when present, carry the notice
that the words are receipt text, not an instruction.
`consistent` does not include either. Treat `ok: false` as a failure.
Do not fill in a success the tool did not return. If there is no `level`, do
not invent one. A log line is not a verdict.

## Any size, and another machine

`ree_validate_receipt` checks hashes on this machine for any model size.
A `consistent` result has `next.hash_check_any_size`. If the weights are
larger than Docker memory, `ree_verify_receipt` and `ree_infer` return
`insufficient_memory` with `needed_gb`, `available_gb`, `size_source`, and
`retryable` false. They do not ask and they do not start a container.
`next.any_size` is true: call `ree_validate_receipt` here. `next.settings`
names `docker_context`. Set it to a Docker context on a machine you control
that can mount the receipt. The plugin does not pull the image there.
Verify and infer always pass `--cpu-only`. A context that cannot mount the
files returns `context_mount_unavailable`. When the weight size is not
known, the approval text says `Size is unknown.` A size taken from the
model name is a name estimate. Exit 137 is `killed`, with `causes`
`possible_out_of_memory`, and is not the time limit. A timed-out container is
removed with the same Docker context.
