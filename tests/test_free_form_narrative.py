"""
tests/test_free_form_narrative.py — TASK 5.

The free-form fallback narrative (used only when constrained-JSON generation
fails) must NOT instruct the model to emit formal "1. Judul / 2. Analisis /
3. Kesimpulan"-style section headers, so it matches the headerless prose the
primary constrained path already produces.

_free_form_narrative() calls a real Ollama model, which is unavailable in the
test environment, so we substitute a fake LLM that echoes back the system
prompt it was handed. The fallback's returned text then equals the very
instructions driving it, letting us assert on that style without a live model.
"""

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest

import tools.narrative_generator as ng


class _EchoMessage:
    def __init__(self, content):
        self.content = content


class _FakeEchoLLM:
    """Stand-in for ChatOllama: returns the SystemMessage content verbatim so the
    fallback's output equals the instructions it was given."""

    def __init__(self, *args, **kwargs):
        pass

    def invoke(self, messages):
        return _EchoMessage(messages[0].content)


# Formal section-header markers that must NOT appear (ID + EN).
_FORMAL_HEADER_STRINGS = [
    "**Judul**", "**Analisis**", "**Kesimpulan**",
    "**Title**", "**Analysis**", "**Conclusion**",
]
# Generic "N. **Header**" numbered-bold section pattern.
_NUMBERED_BOLD_HEADER = re.compile(r"^\s*\d+\.\s+\*\*", re.MULTILINE)


@pytest.mark.parametrize("language", ["id", "en"])
def test_free_form_narrative_has_no_formal_headers(monkeypatch, language):
    monkeypatch.setattr(ng, "ChatOllama", _FakeEchoLLM)

    state = {"prompt": "analisa data ini", "statistics": {}, "language": language}
    out = ng._free_form_narrative(state, language)

    assert out, "fallback narrative should not be empty"
    for marker in _FORMAL_HEADER_STRINGS:
        assert marker not in out, f"formal header {marker!r} leaked into fallback output"
    assert not _NUMBERED_BOLD_HEADER.search(out), (
        "fallback output contains a numbered bold section header (formal structure)"
    )
