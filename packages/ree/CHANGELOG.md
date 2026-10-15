# Changelog

## Unreleased

Receipt checks follow the published REE receipt description.
`execution.device_name` allows spaces, including the documented example
`NVIDIA A100`. `input.prompt` and `output.text_output` are bounded by the
1 MiB file limit, not by a shorter cap. A receipt whose version is not
`2.0.0` returns `unsupported_receipt_version` and does not start a container.
Failure kinds are not chosen by searching message text.

`ree_verify_receipt` runs official validate before asking for approval.
An inconsistent receipt does not ask. Approval that was not granted does
not claim that the user refused. A timeout sets `retryable` false.
Exit 137 is `killed`, not a time limit. `reexecuted_and_text_match`
includes `not_compared`. Settlement
checks include `binding` `not_checked`: this plugin does not check that a
receipt was used for a settlement.

Returned receipt files are mode 0600 and their directory is mode 0700.
The manifest requires Hermes 0.21.6 or newer. It was loaded on 0.21.7.
Version 0.21.6 was not loaded. Checked on macOS (Colima). Linux is
unmeasured.

Before approval, verify and infer compare weight bytes with
`docker info` `MemTotal`. A model that does not fit returns
`insufficient_memory` and does not ask. Unknown size does not stop the
question. `docker_context` selects another Docker context, and cleanup
uses that same context. `DOCKER_HOST` is named when it is the destination.
Verify and infer always pass `--cpu-only`. Existing cache directories are
not chmodded. The plugin does not pull. Hash validation still runs on this
machine for any model size.
