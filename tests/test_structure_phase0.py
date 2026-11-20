"""Phase 0: checks that the repo structure and basic rules are in place."""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

FILES = [
    "CLAUDE.md",
    "SPEC.md",
    "PROGRESS.md",
    "README.md",
    "docs/DECISIONS.md",
    ".gitignore",
    ".env.example",
    "src/__init__.py",
    "tests/__init__.py",
]

DIRECTORIES = ["docs/sessions", "src", "tests"]


def test_phase_0_files_exist():
    missing = [f for f in FILES if not (ROOT / f).is_file()]
    assert missing == []


def test_phase_0_directories_exist():
    missing = [d for d in DIRECTORIES if not (ROOT / d).is_dir()]
    assert missing == []


def test_env_is_in_gitignore():
    lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in [line.strip() for line in lines]


def test_env_example_has_no_values():
    lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    variables = [line for line in lines if line.strip() and not line.startswith("#")]
    assert variables, ".env.example must declare at least one variable"
    for line in variables:
        key, separator, value = line.partition("=")
        assert separator == "=", f"line without '=': {line!r}"
        assert value.strip() == "", f"{key} must not have a value in .env.example"


def test_no_real_env_in_the_repo():
    try:
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", ".env"],
            cwd=ROOT,
            check=False,
            capture_output=True,
        )
        inside_repo = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=ROOT,
            check=False,
            capture_output=True,
        )
    except FileNotFoundError:
        pytest.skip("git is not available")
    if inside_repo.returncode != 0:
        pytest.skip("not a git repository")
    assert result.returncode != 0, ".env must not be tracked by git"


def test_claude_md_states_the_hard_restrictions():
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Nunca se sube ni se publica nada" in text
    assert "agnóstico a la fuente" in text


def test_decisions_records_the_first_four_decisions():
    text = (ROOT / "docs" / "DECISIONS.md").read_text(encoding="utf-8")
    for decision in ("D1", "D2", "D3", "D4"):
        assert f"## {decision} ·" in text
