# Hermes plugins for Gensyn Delphi and REE

Two plugins that connect [Hermes Agent](https://github.com/NousResearch/hermes-agent) to Gensyn Delphi and Gensyn REE. Each directory under `packages/` is one self-contained plugin.

Community plugin maintained by TakeshiTGAL. Not made by Gensyn. The public repository is https://github.com/TakeshiTGAL/hermes-gensyn-plugins. Catalog drafts in `catalog/` use that URL. Their `sha` is forty zeros until the catalog pull request sets the pin. Card images are not in this repository.

## The plugins

| Plugin | Tools | Needs | What it does |
| --- | --- | --- | --- |
| [`hermes-gensyn-delphi`](packages/delphi/) | `delphi_list_markets`, `delphi_get_market`, `delphi_get_positions`, `delphi_query_subgraph`, `delphi_compute_edge`, `delphi_quote_buy`, `delphi_quote_sell` | Node.js 20.18 or newer, the pinned Delphi SDK, and `DELPHI_API_ACCESS_KEY` for markets, positions, and a live edge. Quotes and subgraph history do not use that key. Linux and macOS. Hermes 0.21.4 or newer. | Seven read-only tools for static markets, public positions, fixed history, an arithmetic edge, and collateral quotes. Not investment advice. |
| [`hermes-gensyn-ree`](packages/ree/) | `ree_validate_receipt`, `ree_verify_receipt`, `ree_infer` | Docker, and the local image `gensynai/ree:v0.8.0` that you pull yourself. Linux and macOS. Hermes 0.21.6 or newer. | Three tools that check or create one REE receipt on this computer. |

## Install

From this checkout, copy one plugin directory into the active Hermes profile and enable it. `hermes plugins install` on the Hermes versions these plugins require takes a Git URL or a catalog name. After a catalog pin exists, the command is `hermes plugins install <name>`. These drafts are not in the catalog.

```bash
export HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
python3 - <<'PY'
import os
import shutil
from pathlib import Path

home = Path(os.environ["HERMES_HOME"]) / "plugins"

def install(source, name):
    dest = home / name
    shutil.rmtree(dest, ignore_errors=True)
    shutil.copytree(
        source,
        dest,
        ignore=shutil.ignore_patterns(
            "tests", "__pycache__", "smoke.py", "*.test.mjs", ".pytest_cache", ".venv",
        ),
    )

install("packages/delphi", "hermes-gensyn-delphi")
install("packages/ree", "hermes-gensyn-ree")
PY
(
  cd "$HERMES_HOME/plugins/hermes-gensyn-delphi"
  npm ci --ignore-scripts
)
hermes plugins enable hermes-gensyn-delphi
hermes plugins enable hermes-gensyn-ree
```

There is no `pip install`. Python code in both plugins uses the standard library only. The Delphi SDK is installed with `npm ci --ignore-scripts` from the pinned lockfile.

Tools are enabled on every Hermes surface by default, including gateways. A person admitted by a gateway can call them with the owner's key, and can start REE containers on the owner's Docker daemon. Disable tools per surface with `hermes tools`.

Set `DELPHI_NETWORK` to `testnet`, `mainnet`, or `competition-testnet`. Keys for testnet and competition-testnet are issued at https://delphi-api-access.gensyn.ai/. Mainnet keys are issued at https://api-access.delphi.fyi/. Then run `hermes gensyn doctor` and `hermes ree doctor`. Doctor does not pull an image and does not send a trade.

## REE binary license

The REE binary is under Gensyn's REE-Binary-License. This repository does not bundle that image and does not pull it. You pull it yourself:

```bash
docker pull gensynai/ree:v0.8.0
```

That pull is your consent. The plugin starts only the pinned digest and passes `--pull never`.

## What these plugins do not do

Delphi here is read-only. Quotes are reads. There is no buy, sell, redeem, or other transaction. An edge is a subtraction, not a recommendation. This is not investment advice. A second decode, HTML entities, and marks that are not controls or format characters are outside this check.

REE checks a receipt the user already has, or writes a new receipt from a small local model. It does not submit a dispute and it does not trade. Official validate and official verify do not stand behind `text_output`, `finish_reason`, `token_count`, `model.name`, or `ree_version`.

## Repository layout

```
packages/delphi/     plugin.yaml, __init__.py, pyproject.toml, README.md, tests/, LICENSE
packages/ree/        the same, plus skills/
catalog/             catalog drafts (sha set in the catalog pull request)
```

Installing one plugin does not require the other directory. The plugins do not import each other.

## Development

Clone [hermes-agent](https://github.com/NousResearch/hermes-agent) beside this repo, then run a plugin's suite from inside its directory:

```bash
cd packages/delphi
npm ci --ignore-scripts
npm test
HERMES_AGENT_REPO=../../../hermes-agent PYTHONPATH=../../../hermes-agent python -m pytest -q
hermes plugins validate .

cd ../ree
HERMES_AGENT_REPO=../../../hermes-agent PYTHONPATH=../../../hermes-agent python -m pytest -q
hermes plugins validate .
```

If `hermes-agent` is not a sibling of this repo, point both variables at that checkout. CI does that on Linux and macOS against current Hermes core. Windows is not a target. Tests that need a local Hermes harness skip, with a reason, when those interpreters are absent. The real Docker test runs only when `REE_LIVE=1`.

Supported operating systems are Linux and macOS. Do not commit an API key.

## Catalog drafts

`catalog/hermes-gensyn-delphi.yaml` and `catalog/hermes-gensyn-ree.yaml` are drafts for the catalog pull request. `repo` is https://github.com/TakeshiTGAL/hermes-gensyn-plugins. `subdir` is `packages/delphi` or `packages/ree`. `sha` is forty zeros. That value is not a pin. The catalog pull request sets the 40-character commit. `requires_hermes` is a quoted string. There is no `image` field. Card images are not in this repository.
