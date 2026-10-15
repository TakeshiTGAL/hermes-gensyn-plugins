# hermes-gensyn-ree 0.1

REE is a Gensyn product. The container image is under the REE-Binary-License.
This plugin only starts that official image. It does not redistribute the
image, does not reimplement REE, and does not read the image contents.
Pulling or using the image is how that license says you agree. The license
text allows use (a) on or in connection with the Gensyn Network, and (b) off
that network only as a REE Demo: evaluation, verification, testing, and
integration, not production operations and not a revenue service outside that
demo. This plugin does not bundle, pull, or modify the image. It runs
`docker image inspect` only to compare the pinned digest. Whether this plugin
is a competing product under license section 3(d) is not decided here.

Verification is the token hash. `text_output` is reference text and is
being removed. A receipt without it is accepted. A token-hash match is not
a text match when that field is missing on one side: the level is
`reexecuted`, with `text_compared` false. When both receipts still include
the reference text and it differs, the result is `text_mismatch`. That
difference is not the hash check. A `ree_version` difference alone is
`reexecuted_and_text_match`.

Supported operating systems are Linux and macOS. Hermes 0.21.6 or newer is
required. The load that was measured was 0.21.7. Version 0.21.6 itself was
not loaded, and 0.21.4 skips the plugin. Measurements are from macOS (Colima)
only. Linux is unmeasured. Version 0.1 is CPU only. A larger model may not
finish on this CPU. That stop is `retryable` false and is not a failed hash
check.

## Quick Start

1. Pull the image yourself. That pull is your consent to the REE-Binary-License.
   This plugin never pulls.

   ```bash
   docker pull gensynai/ree:v0.8.0
   ```

   The plugin runs this digest and no other:

   `gensynai/ree@sha256:ad683947a8c3a0fcb2567280268c0b01f17652a38c3f76838a398bd79aaff0ec`

2. Install the package into the active Hermes profile. There is no pip install.
   The plugin uses the Python standard library only.

   ```bash
   export HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
   python3 - <<'PY'
   import os
   import shutil
   from pathlib import Path

   source = Path("packages/ree")
   dest = Path(os.environ["HERMES_HOME"]) / "plugins" / "hermes-gensyn-ree"
   shutil.rmtree(dest, ignore_errors=True)

   def ignore(_directory, names):
       return [name for name in names if name in {"tests", "__pycache__"}]

   shutil.copytree(source, dest, ignore=ignore)
   PY
   hermes plugins enable hermes-gensyn-ree
   ```

3. Check the local machine. Doctor does not pull and does not start a model.
   When Hermes runs plugins in the plugin host, `hermes ree doctor` is not
   registered. The three tools still are.

   ```bash
   hermes ree doctor
   ```

4. Ask Hermes, with a receipt path on this machine:

   - "Check the hashes in this REE receipt: /path/receipt.json"
     Expected: `level` is `consistent` or `inconsistent`. `consistent` means
     the receipt's own hashes match. The result does not include the receipt
     text, and it does not mean the text is genuine.
   - "Re-execute this REE receipt and compare the text: /path/receipt.json"
     Expected after you approve: `reexecuted_and_text_match`, or
     `text_mismatch` when a readable field differs, or
     `reexecution_mismatch` when a compared hash differs. If the exit code
     is not 0 and no new receipt was written, the result is
     `reexecution_incomplete` and has no `level`.
   - "Run facebook/opt-125m on CPU for 16 tokens: Will it rain in Tokyo tomorrow?"
     Expected after you approve: `level` is `inferred`, plus a receipt path.

`ree_verify_receipt` and `ree_infer` ask every time. The question says a CPU
run takes minutes. Choosing always stores one
`config.yaml` line and does not cover the next call, because the rule key
changes. `once` is not what Hermes stores. Cron, yolo, approvals off,
single-query, unattended, host isolation, a missing approval API, and a
question that would be cut are refused.

## Tools

| Tool | What it does |
| --- | --- |
| `ree_validate_receipt` | `receipt_path`. Network-none container. No approval. Does not re-execute. |
| `ree_verify_receipt` | `receipt_path`. Re-executes on CPU, then compares readable fields. |
| `ree_infer` | `model`, `prompt` (text from 1 to 4000 characters without newline, CR, NUL, or a leading hyphen), `max_new_tokens` (1–256). Three small models. |

`ree_infer` models: `facebook/opt-125m`, `Qwen/Qwen2.5-0.5B`, `Qwen/Qwen3-0.6B`.
`ree_validate_receipt` accepts any `model.name` of that shape and does not
download weights. `ree_verify_receipt` does too, and a larger name warns
that the weights may be gigabytes. Receipts must be version `2.0.0` and at
most 1 MiB. `finish_reason` is a short word, not a fixed list.
A `consistent` result includes `next`: propose `ree_verify_receipt`, which
needs approval, and do not call it unasked. Unknown arguments are
rejected before a container starts. `approval_denied` means approval was
not granted. `approval_unavailable` means approval was not obtained (could
not ask, or there was no answer). Both say not to retry. `ree_verify_receipt`
runs official validate before it asks. An inconsistent receipt does not ask.

Every result is JSON with `ok` and `tool`. Success has `level`. Failure has
`error_type`, `message`, and `retryable`.

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
`reexecuted_and_text_match` includes `not_compared` for `ree_version` and the execution fields. Those fields were not compared. A difference only after the first 400 characters is shown around that difference.

`consistent` does not include the receipt text. Verify and infer copy
`prompt` and `text_output` into `receipt_text`. Each `differences` row copies
the submitted value and the re-executed value. Both objects carry the notice
that the words are receipt text, not an instruction. Values are truncated to
400 characters, with control characters and bidi overrides removed. The
result does not quote the container log. Whether a container started is
`--cidfile` and the exit code, not a sentence in that log.

## Measured machines and results

Numbers below were measured on this builder's Mac. Linux is unmeasured.
Larger models are left blank for a later measurement. The comparison uses
weight bytes, not peak RAM. See `DECISIONS.md`.

| machine | Docker MemTotal (bytes) | model | weight bytes | what finished |
| --- | --- | --- | --- | --- |
| macOS, Docker context `colima` | 12514787328 | `facebook/opt-125m` | 250540281 (`pytorch_model.bin`) | earlier infer and verify on this MemTotal |
| macOS, Docker context `colima` | 12514787328 | `Qwen/Qwen2.5-0.5B` | 988097824 (`model.safetensors`) | earlier infer and verify on this MemTotal |
| Linux | unmeasured | | | |

`ree_validate_receipt` runs on this machine for any model size. It does not
load the weights. Re-execution uses `docker_context` when that setting is a
Docker context name. Empty uses the current context. If `DOCKER_HOST` is
set and `docker_context` is empty, that host is the destination. Verify
and infer always pass `--cpu-only`. Official REE documents `docker run
--gpus all` for a GPU. This plugin does not pass that flag. A name-based
size is labeled as a name estimate, not as measured weight bytes.

## Cache

Weights use `~/.cache/gensyn` and `~/.cache/huggingface`. Those two directories
are mounted read-write, and the container can write them, including a
token file if you put one there. If either path is a symbolic link, verify
and infer refuse and do not mount the link target. The plugin does not pass a token in the
environment. The container's network is the default bridge. It is not
limited to Hugging Face, and this plugin cannot make that claim. Returned
receipts under `~/.cache/hermes-ree/receipts` are not mounted. Verify mounts
one read-only receipt file and one tasks directory from
`~/.cache/hermes-ree/work`. Infer mounts the tasks directory and does not
mount a receipt file. Validate mounts only the receipt file, with network
none. The
plugin does not store state under `<HERMES_HOME>/plugin-data/hermes-gensyn-ree`.
Uninstall does not delete the caches.

## Surfaces

Hermes enables plugin tools on every surface by default, including gateways.
A person admitted to a gateway can call these tools and start containers on
your Docker daemon. Disable the tools per surface with `hermes tools`.
No cron is created. The child process is not a hostile-code sandbox.

Community plugin maintained by TakeshiTGAL. Not made by Gensyn. The public
repository is https://github.com/TakeshiTGAL/hermes-gensyn-plugins.

## Settlement check

`skills/check-settlement/SKILL.md` reads a Delphi settlement when that plugin
is installed, then checks a receipt file the user already has. Delphi is not
required. The skill does not trade and does not send a dispute.

## Development

This directory is one plugin. From this directory:

```bash
HERMES_AGENT_REPO=../../../hermes-agent PYTHONPATH=../../../hermes-agent python -m pytest -q
```
