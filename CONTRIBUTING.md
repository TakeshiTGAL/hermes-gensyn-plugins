# Contributing

Each directory under `packages/` is one self-contained Hermes plugin. `packages/delphi` is Delphi 0.2-live. `packages/ree` is REE 0.1. They do not import each other.

## Making a change

1. Clone this repo and [hermes-agent](https://github.com/NousResearch/hermes-agent) side by side.
2. Work inside one plugin directory and run its suite against core:

   ```bash
   cd packages/delphi
   npm ci --ignore-scripts
   npm test
   HERMES_AGENT_REPO=../../../hermes-agent PYTHONPATH=../../../hermes-agent python -m pytest -q
   hermes plugins validate .
   ```

   For REE, skip the npm lines. The same `pytest` and `validate` commands apply in `packages/ree`.
3. Keep the plugin inside its specification. Do not add tools, settings, or branches that the specification does not name. Delphi stays read-only. REE does not pull, bundle, or inspect the image.
4. Open a change that touches one plugin. CI runs that plugin on Linux and macOS against current core. Windows is not run, because the manifests do not list it.

Python runtime code uses the standard library only. Do not add a `pip install` line to a README. The only runtime Node dependency is `@gensyn-ai/gensyn-delphi-sdk` 2.1.0, pinned in `packages/delphi/package-lock.json`.

Supported networks for Delphi are testnet, mainnet, and competition-testnet. Supported operating systems are Linux and macOS. Never commit an API key.

## Releasing

The public repository is https://github.com/TakeshiTGAL/hermes-gensyn-plugins. Community plugin maintained by TakeshiTGAL. Not made by Gensyn. A release is a catalog pin, in a pull request on hermes-agent that sets `sha` in the catalog entry. The drafts in `catalog/` use forty zeros for `sha` and are not that pull request. A pin that adds tools, hooks, or dependencies asks users to consent again, so those ship as their own pin.

## Tests that need a local machine

`packages/delphi/tests/test_host_dispatch.py` calls the Hermes interpreters in a local harness. When those interpreters are absent, the test skips and names that reason. `packages/ree/tests/test_live_docker.py` runs only when `REE_LIVE=1`. CI does not set that variable and does not mount a harness.
