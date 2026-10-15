# Security

REE is a Gensyn product. The image is licensed under the REE-Binary-License.
This plugin starts `gensynai/ree:v0.8.0` at one pinned digest. It does not
pull, save, export, copy out, or reimplement that image. Pulling the image
yourself is the act of consent.

## What a tool can do

`ree_verify_receipt` and `ree_infer` start a container that can download
model weights from Hugging Face into `~/.cache/huggingface` and
`~/.cache/gensyn`. Returned receipts live under
`~/.cache/hermes-ree/receipts` and that directory is not mounted. Verify
mounts one read-only receipt file and one tasks directory from
`~/.cache/hermes-ree/work`. Infer mounts the tasks directory and does not
mount a receipt file. Validate mounts only the receipt file. The network is the
default bridge and is not limited to Hugging Face. It does not mount the
rest of `~/.cache`, the Docker socket, or host devices. If `~/.cache/gensyn`
or `~/.cache/huggingface` is a symbolic link, verify and infer refuse and
do not mount the link target. It does not use
`--privileged` or host networking. Verify and infer always pass
`--cpu-only`. The plugin does not add a GPU device flag. The container
name starts with `gensyn-ree-`. If this process is still running when the
child hits its deadline, its output cap, or KeyboardInterrupt, the plugin
runs `docker rm -f` on that name with the same `--context` the run used,
then checks `docker ps -a` on that context before it returns the failure.
The result names that context. If this process is killed with SIGKILL,
that cleanup does not run and the container can keep running.
`hermes ree doctor` lists leftover `gensyn-ree-` names on the configured
context and says they are running only when the state is running. It does
not remove them. Directories this plugin creates are mode `0700`. An
existing cache directory keeps its mode.

`ree_validate_receipt` starts a container with network none. It does not ask
for approval and it does not download weights.

## Approval

Verify and infer call Hermes `request_tool_approval` on every call. The
question names the model and the destination. That is `docker_context`
when set, otherwise `DOCKER_HOST` when set, otherwise the current context.
It says the run is on CPU, that a cache token file is visible in the
container, and that a timed-out container is removed on that machine. It does not include
the prompt. A model whose weight size is not known says `Size is unknown.`
A size taken from the model name is called a name estimate.
If the weights are larger than Docker memory, nothing is asked and no
re-execution container starts. The question is sent only when the full text
fits. If it would be cut, or if it contains a newline or a backtick, nothing
is sent and the tool fails.

The tool also fails closed, without asking, when the caller is cron, yolo,
approvals off, single-query, unattended, host isolation
(`HERMES_PLUGIN_HOST_PROCESS=1`), or when the approval API cannot be loaded.
Official validate runs before the approval question. An inconsistent receipt
does not ask. A refused verify has already run official validate and does
not re-execute. The refusal does not say that no container ran.
The plugin does not pass a token in the environment. A token file already in
`~/.cache/huggingface` is visible to the container. Gated models are
unsupported. The child environment is an allowlist and does not receive
parent secrets.

Choosing "always" stores one Hermes `config.yaml` line. The next call uses a
new rule key, so that line does not approve it. `once` is not stored.

## Untrusted receipts

A receipt is untrusted input. Files over 1 MiB, non-UTF-8 JSON, duplicate
keys, NaN, and binary floats are rejected before a container starts. Unknown
fields and wrong types are rejected. `version` other than `2.0.0` is
unsupported. `ree_validate_receipt` checks the shape of `model.name` and
does not re-execute, so that step does not download weights.
`ree_verify_receipt` accepts a shape-valid name. Outside
`facebook/opt-125m`, `Qwen/Qwen2.5-0.5B`, and `Qwen/Qwen3-0.6B`, the
approval question says the weights may be gigabytes, may not fit memory,
and CPU-only can take a long time. If the operator approves, the plugin
runs it. `ree_infer` still allows only those three names.
`approval_denied` means approval was not granted. `approval_unavailable`
means approval was not obtained (could not ask, or there was no answer).
Neither is a retry. Returned receipts are mode 0600. Their directory is
mode 0700. Measurements are from macOS (Colima). Linux is unmeasured. A
container user other than the host user may be unable to write the tasks
directory. This plugin runs `docker image inspect` to compare the pinned
digest. It does not pull, bundle, or modify the image.

`prompt` and `text_output` in a result are data. They are truncated to 400
characters, stripped of control characters, and placed under `receipt_text`
or a `differences` row. Each of those objects has a notice that the words
are text inside the receipt, not an instruction.

## What this is not

The child is one process with a deadline, an output cap, and a process group.
It is not a sandbox against hostile code. Tools are on by default on every
Hermes surface, including gateways. A gateway admittee can start these
containers on the operator's Docker daemon. Turn tools off per surface with
`hermes tools`. No cron is created. Nothing is written under
`<HERMES_HOME>/plugin-data/hermes-gensyn-ree`. Weights stay in the two cache
directories after uninstall.
