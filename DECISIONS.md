# Decisions

## This repository

Delphi 0.2-live is `packages/delphi`. REE 0.1 is `packages/ree`. Each
directory is one plugin, with its own `plugin.yaml`, `__init__.py`,
`pyproject.toml`, `README.md`, `tests/`, and `LICENSE`. They do not import
each other. AXL is not in this checkout. Decisions that belong only to REE
stay in `packages/ree/DECISIONS.md`. The list below is the Delphi scope
record.

## Scope precedence

The Delphi 0.2-live specification for this release is the precedence record. The following
requirements were broader and are intentionally narrowed, one conflict per
line:

- Requirement 5.1 asks for seven or more tools; 0.2-live provides exactly seven.
- Requirement 5.1 mentions quotes; 0.2-live adds read-only quotes, not trades.
- Requirement 5.1 mentions write and balance paths; SCOPE excludes them.
- Requirement 5.1 gives market list probabilities; SCOPE returns static rows.
- Requirement 5.1 gives market detail dynamic fields; SCOPE returns static rows.
- Requirement 5.1 allows raw GraphQL; SCOPE permits three fixed modes only.
- Requirement 6 discusses write approval; SCOPE has no write path to approve.
- Requirement 7 asks doctor to connect; SCOPE makes doctor network-free.
- Requirement 7 asks doctor for a balance; SCOPE has no balance or signer.
- Requirement 5.1 asked for execution; 0.2-live adds quotes only, not trades.
- Requirement 9 describes a broader family; SCOPE implements Delphi only.
- Requirement 10 asks `post_tool_call`; SCOPE uses `transform_tool_result`.
- Requirement 10 anticipates REE and AXL. This checkout ships REE beside Delphi. AXL is not in this checkout.

## SDK contract

The only runtime Node dependency is `@gensyn-ai/gensyn-delphi-sdk` 2.1.0.
Its lockfile integrity is:

`sha512-VfvNyesDXmOEsAUVcbjKyReo7kbM2VbGj9oaImcTaVinBkbWmE7CitSHry9RX7NuNtGUs43Me6AgoNdjP/jyig==`

Market and position field names and types are copied from the SDK 2.1.0
declarations. The bridge calls that SDK for markets, positions, history,
quotes, and a live edge. This package
does not implement an ABI, a signing account, or a transaction.

SDK 2.1.0 reads a live price only with a signer. Upstream probabilities are
the float64 values that SDK returns. The bridge carries them with `String(n)`.
`delphi_compute_edge` accepts either two decimal arguments, which reserve
nothing, or `outcome_idx` plus exactly one of `market_id` or
`market_address`, which reserve 3 fetches. Both names are the 0x id
`getMarket` already takes. `listMarkets` has no appMarketId filter, so a
UUID is `bad_format` and is not scanned. `outcome_idx` starts at 0.
Quotes
reserve 4. Those counts were measured on testnet on 2026-10-11: a cold
`quoteBuy` plus collateral decimals made 4 requests to
`gensyn-testnet.g.alchemy.com`, and a priced `getMarket` made 1 API request
plus 2 RPC requests. The bridge passes `randomBytes(32)` as `privateKey`.
`signerType` is `private_key`, the documented value. `DelphiClient.js`
uses `createPrivateKeySigner` for every type other than the CDP default.
The key is not stored. Version 0.2-live does not
accept `competitionId`, because a returned market row has no field that would
let the plugin verify that filter.

The fetch gate allows the two Delphi API hosts, Goldsky, and the Alchemy RPC
hosts `gensyn-testnet.g.alchemy.com` and `gensyn-mainnet.g.alchemy.com`.
Quotes and live prices use Alchemy. The gate strips the API key header on
every host that is not a Delphi API host and refuses redirects. The child starts in
an empty directory so the SDK does not load a working-directory dotenv file.
Network, wallet, and key presence are read by one function. The profile
scope wins over the process environment. Tools do not assign those names.

## Boundaries

All inputs enter through `service.dispatch`. All known table rows enter through
`contract.validate`. Every bridge response and requested identity is checked
by `service.accept_bridge`. Every public success and failure leaves through
`service.egress`, which applies an output allowlist and a recursive secret scan.

`process.run_child` is the only subprocess implementation.
`rate.reserve` is the only rate-limit implementation. The limit is process
local by design: 30 reservations per 60 seconds, shared across threads. Failed
work does not return a reservation.

The plugin stores no cache, counter, or other state in
`<HERMES_HOME>/plugin-data/hermes-gensyn-delphi`.

## Hermes behavior

Hermes 0.21.4 and the current reference both retain the return value of
`transform_tool_result`. After a successful list, market, or history read, the
hook puts `creator_notice` first. After a successful `delphi_compute_edge`, it
adds `learning_summary`. It does not use `post_tool_call`.

Tools are enabled on every Hermes surface by default, including gateways, until
an operator disables them per surface with `hermes tools`.

## Response fields kept narrower than `string`

The SDK 2.1.0 `.d.ts` is the source of response types. A field is narrower
here only when this plugin assigns meaning, or when a local bound is required.
Fixed word lists copied from one recorded page are not used.

| Field | SDK type | This plugin | Why it is narrower |
| --- | --- | --- | --- |
| `status` | `"open" \| "awaiting_settlement" \| "settled" \| "expired" \| "failed"` | the same five, including `failed` | not narrower than the SDK |
| `category` | `string` | `^[a-z0-9][a-z0-9_-]{0,31}$` | shape only; the six example words in the SDK comment are not a closed set |
| `orderBy` (request) | `string` | `liquidity`, `created`, `settles_at` | those are the values the SDK documents; others are not sent |
| `id` | `string` | `0x` and 40 hex digits | API market ids are addresses, so two ids can be compared |
| `appMarketId` | `string` | UUID | the app URL's last segment is that id |
| `marketUrl` | `string` | the three documented app hosts | a row must belong to the selected network |
| `proof`, `question`, `outcomes`, `metadataUri`, `fetchResponseStatus`, `error` | `string` or `string \| null` | string up to 1 MiB, or null where the SDK allows null | memory bound, not a word list; characters stay free text; `proof` over 64KB is `proof_too_large` |
| `question`, `outcomes`, `model_identifier`, `proof_text` (public) | creator `string` | untrusted box, 240 characters, newlines and tabs become one space | the creator's text is not an instruction |
| `tradingFee` | `string \| null` | unsigned integer string or null | the API sends an integer string where `1e18` is 100% |
| `spotImpliedProbabilities` | `number[]` | decimal strings from 0 to 1 | the SDK returns float64; the bridge carries `String(n)` |
| `proof_kind` | not an SDK field | `empty`, `creator_free_text`, `ree_receipt_json` | this plugin assigns the meaning from the JSON shape only |
| `error_type` | not an SDK field | the fixed set in `spec.py` | this plugin assigns the meaning; HTTP status comes from a numeric `status` or the SDK prefix `API request failed (NNN)`, `Subgraph request failed (NNN)`, or `Health check failed (NNN)` |

Argument text is not searched for 401, 403, or 429. `auth` is used only for
operations that send the API key.

## Publication

The package name follows the requested Hermes package name. The public
repository is https://github.com/TakeshiTGAL/hermes-gensyn-plugins. Community
plugin maintained by TakeshiTGAL. Not made by Gensyn.
