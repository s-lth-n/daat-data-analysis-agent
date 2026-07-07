"""
tests/test_config.py

Proves Settings() resolves its .env independently of the process's current
working directory: config.model_config["env_file"] is anchored to config.py's
own directory, not the launch directory. Before this fix the bare relative
"./.env" meant the app (launched from backend/) and the tests (run from the
repo root) could silently load different .env files.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from config import Settings


def _default_language_from(cwd, monkeypatch) -> str:
    """Instantiate a fresh Settings() as if the process were launched from `cwd`."""
    monkeypatch.chdir(cwd)
    return Settings().default_language


def test_env_file_resolution_is_cwd_independent(tmp_path, monkeypatch):
    """
    Two different simulated launch directories must yield the SAME
    default_language. One of them holds a decoy .env with a bogus value that
    must be ignored — proving env_file is resolved against config.py's location,
    not the CWD.
    """
    decoy_cwd = tmp_path / "decoy_launch_dir"
    decoy_cwd.mkdir()
    (decoy_cwd / ".env").write_text("TA_DEFAULT_LANGUAGE=zz\n")

    plain_cwd = tmp_path / "plain_launch_dir"
    plain_cwd.mkdir()

    lang_from_decoy = _default_language_from(decoy_cwd, monkeypatch)
    lang_from_plain = _default_language_from(plain_cwd, monkeypatch)

    assert lang_from_decoy == lang_from_plain, (
        "default_language changed with the CWD — env_file is not anchored"
    )
    assert lang_from_decoy != "zz", (
        "a .env sitting in the CWD was loaded — env_file is still CWD-relative"
    )
