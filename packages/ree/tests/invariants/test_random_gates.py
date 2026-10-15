"""Seeded checks that each gate's invariant holds for more than the audit's examples."""
from __future__ import annotations

import random
from pathlib import Path

import pytest

from contract import MODELS, make_sample, validate
from docker import DockerError, infer_argv, option_problem
from gate import question
from official import log_disagrees

_PASS = "VERIFICATION PASSED: receipt hashes match"
_SEEDS = range(24)


def _noise(rng):
    alphabet = [chr(code) for code in range(32, 127)]
    return "".join(rng.choice(alphabet) for _ in range(rng.randrange(1, 60)))


@pytest.mark.parametrize("seed", _SEEDS)
def test_random_unknown_key_never_validates(seed):
    data = make_sample("receipt")
    data["k" + str(seed)] = seed
    assert isinstance(validate("receipt", data), str)


@pytest.mark.parametrize("seed", _SEEDS)
def test_random_text_does_not_raise(seed):
    rng = random.Random(seed)
    data = make_sample("receipt")
    data["output"]["text_output"] = _noise(rng)
    problem = validate("receipt", data)
    assert problem is None or isinstance(problem, str)


@pytest.mark.parametrize("seed", _SEEDS)
def test_random_unprefixed_noise_does_not_cancel_one_pass(seed):
    rng = random.Random(seed)
    noise = _noise(rng)
    text = noise + "\n" + _PASS + "\n"
    assert log_disagrees(text, "same") is False


@pytest.mark.parametrize("seed", _SEEDS)
def test_random_prompt_stays_one_argv_element(seed):
    rng = random.Random(seed)
    prompt = _noise(rng)
    if option_problem(prompt) or not prompt.strip():
        with pytest.raises(DockerError):
            infer_argv("gensyn-ree-ab", Path("/tmp/tasks"), MODELS[0], prompt, 4, Path("/tmp/cid"))
        return
    argv = infer_argv(
        "gensyn-ree-ab", Path("/tmp/tasks"), MODELS[0], prompt, 4, Path("/tmp/cid"),
    )
    slot = argv.index("--prompt-text")
    assert argv[slot + 1] == prompt
    assert "--privileged" not in argv
    assert "--network" not in argv


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("count", (1, 256))
def test_every_question_fits_and_names_minutes(model, count):
    verify = question("verify", model)
    inferred = question("infer", model, count)
    for text in (verify, inferred):
        assert "Takes minutes" in text
        assert "not limited to Hugging Face" in text
        assert len(text) <= 300
        assert "\n" not in text and "`" not in text
    assert "read-only receipt file" in verify
    assert "no receipt file" in inferred
