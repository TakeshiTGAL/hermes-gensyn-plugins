# Security

This repository has two plugins. Delphi 0.2-live reads markets, positions,
history, an edge, and quotes. REE 0.1 checks or creates one receipt on this
computer. Neither plugin trades, and neither sends a dispute. The sections
below are the facts for each plugin. REE's container rules in full are
`packages/ree/SECURITY.md`, so they are not copied here a second time.

## Delphi

Delphi 0.2-live has seven read-only tools. Quotes and a live probability are
reads. There is no buy, sell, redeem, liquidate, approval, or transaction
path. Write operations remain outside this package.

## Secrets and destinations

The only secret is `DELPHI_API_ACCESS_KEY`. Each call reads that key,
`DELPHI_NETWORK`, and `DELPHI_WALLET_ADDRESS` with
`agent.secret_scope.get_secret`. One Hermes process does not take another
profile's values. `UnscopedSecretError` is not treated as an unset key.
Depending on `DELPHI_NETWORK`, the key
is sent as an HTTPS header only to:

- `delphi-api.gensyn.ai` for testnet and competition-testnet
- `api.delphi.fyi` for mainnet

Keyless subgraph reads go to `api.goldsky.com`. Quotes and live probabilities
go to `gensyn-testnet.g.alchemy.com` or `gensyn-mainnet.g.alchemy.com` without
the API key. For those calls the bridge creates a fundless random key with
`randomBytes(32)`, passes it only to the SDK client, and drops it when the
call returns. The key is not written to a file, an environment variable, a
log, stdout, stderr, or the tool JSON. An argument-only edge does not call
upstream. The API key header is removed
unless the host is one of the two Delphi API hosts above, and redirects are
not followed. The key is not accepted in tool arguments and is not included in
results, exception messages, child argv, or logs. `DELPHI_WALLET_ADDRESS` is a
public address, not a private key.

Failure messages are fixed sentences for each error type. A numeric HTTP
status is the only text taken from an upstream error. Question, outcome,
`model_identifier`, `metadata_version`, and `proof_text` are cut to 240
characters after control and format characters are removed. `proof_truncated`
is set only for `proof_text`.
Other id, hash, address, number, and time columns are strict types. A space,
`%`, `\`, `&`, or a character outside that type makes the whole response fail.

The secret check then looks at the original text, one percent-decode, one
`\uXXXX` decode, and both once in either order. The whole response becomes a
fixed internal error when the API key, or any 12 consecutive characters of it,
appears. The bridge applies the same check to the fundless random key before
it writes JSON. Python holds `DELPHI_API_ACCESS_KEY` to pass it into the
child environment and to scan the response for that key and any 12-character
fragment. It does not hold the fundless random key. The bridge sets
`signerType` to `private_key`. That is the documented local-key value.
`DelphiClient.js` uses `createPrivateKeySigner` for every type other than
`cdp_server_wallet`, so the fundless key is the signer. A second decode, HTML entities,
and marks that are not controls or format characters are outside this check.

## Process boundary

The pinned Delphi SDK runs in one local Node subprocess. The subprocess is not
a hostile-code sandbox. It receives only an allowlisted environment, uses
`shell=False`, starts in a new session, has bounded stdin/stdout/stderr, a
256 MiB JavaScript heap limit, and one 25-second monotonic deadline. Timeout or
output overflow terminates the process group so a grandchild cannot keep a
pipe open.

The bridge calls `@gensyn-ai/gensyn-delphi-sdk`. This package does not
implement an ABI, a contract call, or a transaction. The random key is used
only so the SDK can read a quote or a live probability. The child starts in
an empty directory so SDK startup does not read a working-directory dotenv
file. The child environment never receives a name containing `PRIVATE` or `CDP`.

## Network and rate limit

One Hermes process reserves at most 30 outbound requests in 60 seconds.
Threads share one lock. Separate processes have separate counters. A
reservation is made before work and is not returned when work fails. There is
no daily cap. The bridge does not set viem `retryCount`. SDK retries use
this same fetch gate, so they cannot exceed the reserved count.

The plugin stores no state or cache in
`<HERMES_HOME>/plugin-data/hermes-gensyn-delphi`. It creates no cron, although
a cron configured outside the plugin can invoke its tools. Uninstalling the
plugin does not delete that cron; remove it in the scheduler that created it.
`hermes gensyn doctor` is registered for the in-process host. A Hermes build
that skips CLI commands when `plugins.isolation` is `host` does not install
the command. That absence is not a healthy report.

## Hermes surfaces

Tools are enabled on every Hermes surface by default, including gateways. A
person admitted by a gateway can call them with the owner's API key. Disable
tools per surface with `hermes tools`.

## REE

REE is a Gensyn product. The image is under the REE-Binary-License. This
plugin starts one pinned digest of `gensynai/ree:v0.8.0`. It does not pull,
bundle, save, or export that image. Doctor compares the local digest with
`docker image inspect` and does not unpack the image. Pulling or using the
image is the consent under the REE-Binary-License.

`ree_verify_receipt` and `ree_infer` ask Hermes for approval on every call.
The question is sent only when the full text fits. If it would be cut, nothing
is sent and the tool fails. Cron, yolo, approvals off, single-query,
unattended, host isolation, and a missing approval API are refused before
re-execution or inference. Choosing always stores one config line and does
not cover the next call.

Official validate and official verify do not stand behind `text_output`,
`finish_reason`, `token_count`, `model.name`, or `ree_version`. The plugin's
`text_mismatch` level is the case where those hashes still match and a
readable field differs.

Tools are enabled on every Hermes surface by default, including gateways. A
person admitted by a gateway can start containers on the owner's Docker
daemon. Disable tools per surface with `hermes tools`. Nothing is stored
under `<HERMES_HOME>/plugin-data/hermes-gensyn-ree`. The child is not a
hostile-code sandbox. No cron is created.

## Publication

The public repository is https://github.com/TakeshiTGAL/hermes-gensyn-plugins.
Community plugin maintained by TakeshiTGAL. Not made by Gensyn. Catalog drafts
in `catalog/` use that URL. Their `sha` is forty zeros until the catalog pull
request sets the pin.
