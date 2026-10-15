# Decisions

## Image and license

The only image reference is
`gensynai/ree@sha256:ad683947a8c3a0fcb2567280268c0b01f17652a38c3f76838a398bd79aaff0ec`.
`docker run` is passed `--pull never`. Doctor tells the operator to run
`docker pull gensynai/ree:v0.8.0` and that the pull is consent to the
REE-Binary-License. This plugin does not fetch the image. Doctor and the
unstarted check run `docker image inspect` to compare the pinned digest.

## Validate does not receive `--cpu-only`

Measured on macOS (Colima), `validate --receipt-path` with `--network none` exits 0. Linux is unmeasured.
The same command with `--cpu-only` exits 2:
`gensyn-sdk: error: unrecognized arguments: --cpu-only`.
Validate therefore uses network none and does not pass `--cpu-only`.
Verify and `run-all` do pass `--cpu-only`. Measured on macOS (Colima) with the pinned image.

## What decides a result

The container log does not choose the result. Verify's result is the exit
code plus the new receipt file. The plugin compares
`output.tokens_hash`, `input.prompt_hash`, `input.tools_hash`,
`input.parameters_hash`, `hashes.receipt_hash`, `model.config_hash`, and
`model.commit_hash`. Readable fields are `output.text_output`,
`output.finish_reason`, `output.token_count`, `model.name`, and
`input.prompt`. The table is `VERDICT` in `service.py`. Anything else is
`internal`.

Validate reads only four full lines (`prompt_hash`, `tools_hash`,
`parameters_hash`, `receipt_hash`, each `PASS` or `FAIL`), with an optional
logger prefix. On macOS (Colima) the first line has the prefix and the next three
do not. All four once, all `PASS`, and exit 0 is `consistent`. At least one
`FAIL` and exit 1 is `inconsistent`. Otherwise `validate_incomplete`, with
no `level`. Verify runs that validate first and does not re-execute an
inconsistent receipt.

A container that did not start is `docker_unavailable`, `image_missing`, or
`container_not_started`, from `docker version` and `docker image inspect`
exit codes and from an empty `--cidfile`. The stderr text is not used.
Exit 0 with no receipt, or with two receipts, is `internal`. Exit not 0
with no receipt is `reexecution_incomplete`: hashes were not compared.
An exact prefixed `VERIFICATION PASSED: receipt hashes match` or
`verify failed:` line is read only when it contradicts that file result,
and then the result is `internal`. The table is `DISAGREE` in `official.py`.
A lone `verify failed:` line does not contradict a run that wrote no
receipt. A `VERIFICATION PASSED` line does. The line is not copied into
`message`. On macOS (Colima) both the pass line and `Printing model outputs` are
on stderr, so splitting stdout from stderr would not separate them.

`run-all` succeeds only when the exit code is 0 and the tasks root has one
schema-valid receipt whose prompt is the requested prompt. The text is
`output.text_output` from that file.

## `ree_version` is not a readable field

Official verify of `ree_version` `0.7.0` still exited 0 and wrote `0.8.0`.
That field is not in the readable list, so the level stays
`reexecuted_and_text_match` when the hashes and the readable fields match.
Copied receipt words are returned only from `receipt_text` or a
`differences` row. `_place` adds the notice on those slots and returns
nothing for any other slot.

## Versions and models

The image reports that it recognises receipt versions `2.0.0`, `2.1.0`, and
`2.2.0`. This plugin accepts `2.0.0` only, before a container starts.
`ree_infer` model names are `facebook/opt-125m`, `Qwen/Qwen2.5-0.5B`, and
`Qwen/Qwen3-0.6B`. `ree_validate_receipt` does not re-execute, so
`model.name` is a shape check (one slash, letters, digits, and `._/-`)
and `Qwen/Qwen3-8B` is not rejected there. `ree_verify_receipt` uses the
same shape. The official image is the compatibility check. Outside the
three small names, the approval question adds that the weights may be
gigabytes, may not fit memory, and CPU-only can take a long time. The
question stays within 300 characters, so that warning replaces the longer
small-model sentence. `run-all --help` lists `torch_dtype` as
`float16`, `bfloat16`, and `float32`, and `operation_set` as `default`,
`deterministic`, and `reproducible`. `finish_reason` and `rand_algorithm`
have no closed list in that help, so they are short ASCII words.
`run-all`, `generate`, and `receipt` have no tools flag. The official SDK
can store tool definitions under `input.tools`. A receipt may carry `tools`
null or a list of objects. A nested function object is accepted.

## Where temporary files go

Docker on macOS (Colima) does not see `/tmp` or `/var/folders`. A file bind-mounted
from there appears inside the container as an empty directory. Receipt copies
and tasks directories are therefore created under
`~/.cache/hermes-ree/work` and removed after the call. That directory is not
a cache mount. Verify mounts the one receipt file and the tasks directory.
Infer mounts the tasks directory and does not mount a receipt file. Returned
receipts are
`~/.cache/hermes-ree/receipts/<64 hex>.json`, and that directory is not
mounted. The tasks directory is mode `0700`. A receipt written by the image
on macOS (Colima) is owned by the host user, so the container can write it without
making the directory world-writable. If this process is still alive when the
child stops or KeyboardInterrupt is raised, the plugin runs `docker rm -f`
on the `gensyn-ree-` name. SIGKILL of this process does not run that command.
`hermes ree doctor` lists `gensyn-ree-` names and their state. An exited
container is not described as running. Names are not removed, because
another call may be using one. A refused verify still runs official
validate, which does not ask, and does not run verify. The refusal says
the call was refused. It does not say that nothing ran.
`~/.cache/gensyn` and `~/.cache/huggingface` are mounted only when each
path is a real directory. A symbolic link is refused before verify or
infer starts, so the link target is not mounted.

## Where the new receipt goes

Each verify or infer call gets its own empty tasks directory. The image
writes `receipt_YYYYMMDD_HHMMSS.json` under that tree. The plugin reads the
bytes only when there is exactly one regular file of that name, then deletes
the directory. Infer copies those bytes to
`~/.cache/hermes-ree/receipts/<64 hex>.json` so the returned path
still exists. If that path already exists with different bytes, infer fails.
Exit 0 with zero files or two files is `internal`. Exit not 0 with zero
files is `reexecution_incomplete`. Neither is a success.

## Hermes version

`requires_hermes` stays `>=0.21.6`. The plugin was loaded and run on 0.21.7.
Version 0.21.6 was not available to load. Version 0.21.4 skips the plugin.
`HERMES_PLUGIN_HOST_PROCESS` is refused when it is `1`.
`plugins validate` checks that the spec parses. It does not compare it with
the running version.

## No hook

Results are already the JSON the tool returns. `transform_tool_result` is
not registered. `post_tool_call` is not registered. On a Hermes build that
runs plugins in the plugin host, `hermes ree doctor` is not registered
either. The three tools still are.

## Receipt fields and what this plugin narrows

Published receipt description (docs.gensyn.ai/tech/ree/receipts) gives string,
int, object, or array-or-null. There is no JSON Schema file in that page.
This plugin still refuses a receipt before a container starts. A narrowing
without a reason was removed.

| Field | Published type | This plugin | Why it is narrower, if it is |
| --- | --- | --- | --- |
| `version` | string | `2.0.0`, otherwise `unsupported_receipt_version` | This plugin checks one schema. Other versions are a typed refusal, not a success. The readable head of `model.name` and `prompt` is 5 characters plus `...` when longer, so the tool result does not contain a sentence from the receipt. |
| `ree_version` | string | dotted triple | Untrusted text. Measured versions are dotted triples. |
| `model.name` | string | one slash, limited characters, 128 | The value is copied into the approval question and into `docker run`. |
| `commit_hash` | string | 40 hex digits | Shape used to compare, not one remembered commit. |
| hash fields | string | `sha256:` and 64 hex digits | Shape used to compare. |
| `input.prompt`, `output.text_output` | string | string without NUL. `text_output` may be absent | The 8000 and 20000 caps were removed. The file cap is 1 MiB. Missing `text_output` is accepted. |
| `execution.device_name` | string, example `NVIDIA A100` | 1 to 128 characters, no control characters, spaces allowed | The documented example contains a space. |
| `execution.device_type` | string, examples `cpu`, `cuda` | short token, either letter case | Not a closed list. |
| `finish_reason` | string; the page names `eos_token` and `max_length` | short ASCII word | A real receipt used `stop`. An unlisted word is not refused. |
| `torch_dtype` | CLI names | `torch.float16`, `torch.bfloat16`, `torch.float32` | `run-all --help`. |
| `operation_set` | CLI names | `default`, `deterministic`, `reproducible` | `run-all --help`. |
| sampling numbers | int or number | bounded int, or Decimal from 0 to 2 | Untrusted size. Not an official maximum. |
| `input.parameters.enable_thinking` | bool, optional | bool | Documented. Present only when the caller set it. Included in `parameters_hash` when present. |
| `input.parameters` other keys | object, list not closed | the keys above, plus `enable_thinking` | A key outside this table is refused before a container starts. |
| `input.tools` | array or null | null or a bounded list of objects | Untrusted structure inside the 1 MiB file. |

## Deadlines

Small models (`facebook/opt-125m`, `Qwen/Qwen2.5-0.5B`, `Qwen/Qwen3-0.6B`) use 600 seconds. A 0.5B verify on macOS (Colima) took about 310 seconds. Any other model name uses 1800 seconds. That number is not a measurement of a large model. A timeout is `retryable` false and `progress` `deadline`. Exit 137 is `killed` with `causes` `possible_out_of_memory`, because `docker kill` also exits 137. It is not reported as the time limit. The result includes `elapsed_seconds`. It does not stream progress while the container runs.

## Weight estimate before approval

The suspicious premise was that the `B` or `M` in a model name is the RAM the
re-execution will use. It is not. It is a parameter count. This machine's
receipts used `torch.float16`, which is 2 bytes per parameter. That width is
the dtype, not a measured peak. Peak RAM was not measured, so the plugin does
not multiply by an extra factor.

`needed` bytes are the sum of `*.safetensors` and `*.bin` in the largest
Hugging Face snapshot under `~/.cache/huggingface/hub/models--<org>--<name>/snapshots`
when that sum is greater than 0. Files reached through a symlink that leaves
the snapshot are not counted. If there is no such sum, the last
`<number><B|M>` in the model name is used: `B` is 10^9 parameters, `M` is
10^6, then times 2. If neither exists, the size is unknown and approval is
still asked. The approval text then contains `Size is unknown.`
A size taken from the model name is labeled `Name estimate`, not as
measured weight bytes.

`available` bytes are `docker info --format '{{.MemTotal}}'` for the Docker
context that will run the container. Comparison is those two integers.
`needed_gb` is `needed` rounded up to a decimal gigabyte (10^9).
`available_gb` is `available` rounded down to a decimal gigabyte. The plugin
refuses only when `needed > available`.

Measured on 2026-10-14, context `colima`, `MemTotal` `12514787328`:

| file | bytes | name formula |
| --- | --- | --- |
| `models--facebook--opt-125m` `pytorch_model.bin` | 250540281 | 125×10^6×2 = 250000000 |
| `models--Qwen--Qwen2.5-0.5B` `model.safetensors` | 988097824 | 0.5×10^9×2 = 1000000000 |

A name such as `32B` is 32×10^9×2 = 64000000000 bytes, which is greater than
this `MemTotal`. That refusal is the weight bytes, not a guess about a 32B
model's peak. `Qwen/Qwen3-0.6B` finished earlier on this same `MemTotal`; its
weight file was not in the cache measured above, so that row is not in the
README table.

## GPU flag and Docker destination

Official REE troubleshooting says a GPU needs `docker run --gpus all`, and
`--cpu-only` forces CPU. On this Docker CLI, `docker --context colima info`
still reached Colima when `DOCKER_HOST` pointed at a missing socket, so an
explicit context wins over `DOCKER_HOST`. With no `--context`, `DOCKER_HOST`
is the destination. Cleanup uses the same `--context` as the run. This
plugin always passes `--cpu-only` and does not pass a GPU device flag.
Existing `~/.cache/huggingface` and `~/.cache/gensyn` directories are not
chmodded. Only a directory this plugin just created is mode 0700.

## Not measured

Filling the disk until Docker reports a full disk was not done. Other
containers were running. A stopped daemon was simulated with a missing
socket, not by stopping the running Docker VM.
