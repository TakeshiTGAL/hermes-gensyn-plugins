# Changelog

## Unreleased

A recorded testnet page uses `fetchResponseStatus` `success` and `tradingFee`
as an integer string where `1e18` is 100%. The tool result keeps that string
and adds `trading_fee_percent`. `proof_text` is text the market creator wrote.
`proof_kind` is `empty`, `creator_free_text`, or `ree_receipt_json`.
`ree_receipt_json` is a shape check only (`shape_only`), not a statement
that the receipt was checked. `looks_like_ree_receipt` is true only when `version` is a string and `model`,
`hashes`, `input`, and `output` are objects. `is_ree_receipt` stays false.
JSON that fails those types is clipped into the untrusted box. When they
match, the receipt is kept. The full receipt stays inside `proof_receipt_json`,
an untrusted box (`untrusted_text: true`) whose `text` is the original JSON,
not clipped, and is not left as a bare string outside that box. That text is
also inside `proof_text`. The opening notice covers the box. To check one,
save `proof_receipt_json.text` and call
`ree_validate_receipt`.
`sdk_error` marks an API row whose `error` string is returned as `error`,
the same untrusted box as `question`, or null. A market
whose `mechanism_type` is `lmsr` is `unsupported_market` and says
"This tool does not return a probability for an lmsr market." A market
neither factory claims is `unsupported_market` for trades and settlement.
`verifiable` is a flag the API returns. This
plugin does not check it.
`model_identifier` is free text. A market that is on chain but missing from
the API list is `not_found` and is not retried. A page the SDK types as an
array or null, including an empty wallet, is a success with `count` 0.
`upstream_null` is true only for that null. A body with no `markets` or
`positions` field is `invalid_response`, not a count of 0.

An `invalid_argument` result adds `field`, `problem`, `expected`, and
`allowed_fields` from one table. Those fields do not contain the submitted
value. `delphi_get_market` and a live `delphi_compute_edge` accept exactly
one of `market_id` or `market_address`.
Both are the 0x id. A UUID is `bad_format`. `outcome_idx` starts at 0. With
a key, `delphi_get_market` names it. Without a key, the name is unknown.

A `config` result now adds `missing` (setting names only), `needed_for`,
and `works_without_key`.

`DELPHI_API_ACCESS_KEY`, `DELPHI_NETWORK`, and `DELPHI_WALLET_ADDRESS` are
read on each call with `agent.secret_scope.get_secret`. One Hermes process
does not take another profile's values. `UnscopedSecretError` is not treated
as an unset key. An invalid network or wallet uses one fixed sentence and a
`setting` field. That sentence does not change when the process environment
also has the name. Python holds the API key to pass it to the child and to
scan the response for that key and any 12-character fragment, and does not
hold the fundless random key.
