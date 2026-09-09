"""Tests for reasoning-model chain-of-thought handling in allelio.ai.engine.

PUB-16: a reasoning model (DeepSeek-R1 and its distills, QwQ, Qwen3 in
thinking mode, gpt-oss) emits its private chain-of-thought either inline in
`content` wrapped in <think>/<thinking> tags, or in a sibling field
(`reasoning_content`, `reasoning`). Only ever the stripped answer may reach
check_safety or the rendered explanation -- these tests pin that invariant
directly, including the case that matters most: a diagnostic phrase in the
reasoning must never trip the safety note, and the same phrase in the answer
must always trip it.
"""

import pytest

from allelio.ai.engine import AIEngine, _split_answer_and_reasoning, _strip_reasoning
from allelio.analysis.lookup import ClinVarEntry, VariantResult


def _variant(rsid: str = "rs429358") -> VariantResult:
    return VariantResult(
        rsid=rsid,
        genotype="CT",
        chromosome="19",
        position=44908684,
        clinvar_entries=[
            ClinVarEntry(
                rsid=rsid,
                gene="APOE",
                clinical_significance="Pathogenic",
                conditions="Alzheimer disease",
                review_status="reviewed by expert panel",
            )
        ],
        gwas_entries=[],
    )


class StubClient:
    """Answers with whatever message dict the test hands it."""

    def __init__(self, message: dict):
        self.message = message

    async def chat(self, model, messages, stream=False, **kwargs):
        return {"message": self.message}


def _engine() -> AIEngine:
    engine = AIEngine()
    engine.available = True
    return engine


# --- _strip_reasoning / _split_answer_and_reasoning -------------------------


def test_strip_reasoning_removes_inline_think_block():
    content, reasoning = _strip_reasoning(
        "<think>the user carries a risk allele</think>Here is a plain-English summary."
    )
    assert content == "Here is a plain-English summary."
    assert "risk allele" in reasoning


def test_strip_reasoning_removes_inline_thinking_block_case_insensitive():
    content, reasoning = _strip_reasoning(
        "<THINKING>internal notes</THINKING>The answer."
    )
    assert content == "The answer."
    assert reasoning is not None


def test_strip_reasoning_unclosed_tag_empties_the_answer():
    """A truncated <think> with no close is unfinished reasoning, not an answer."""
    content, reasoning = _strip_reasoning(
        "<think>the model runs out of tokens right here and never finishes"
    )
    assert content == ""
    assert reasoning is not None


def test_strip_reasoning_no_tags_is_a_no_op():
    content, reasoning = _strip_reasoning("A completely ordinary answer.")
    assert content == "A completely ordinary answer."
    assert reasoning is None


def test_split_answer_and_reasoning_separate_field_deepseek_convention():
    message = {
        "content": "The clean, final answer.",
        "reasoning_content": "internal deliberation goes here",
    }
    answer, reasoning = _split_answer_and_reasoning(message)
    assert answer == "The clean, final answer."
    assert reasoning == "internal deliberation goes here"


def test_split_answer_and_reasoning_separate_field_reasoning_key():
    message = {"content": "The final answer.", "reasoning": "private notes"}
    answer, reasoning = _split_answer_and_reasoning(message)
    assert answer == "The final answer."
    assert reasoning == "private notes"


def test_split_answer_and_reasoning_only_reasoning_no_answer():
    message = {"content": "", "reasoning_content": "thought and thought and never answered"}
    answer, reasoning = _split_answer_and_reasoning(message)
    assert answer == ""
    assert reasoning


def test_split_answer_and_reasoning_object_style_message():
    """Ollama's own message type isn't a dict; attribute access must work too."""

    class Message:
        content = "<think>hidden</think>Visible answer."
        reasoning_content = None
        reasoning = None

    answer, reasoning = _split_answer_and_reasoning(Message())
    assert answer == "Visible answer."
    assert "hidden" in reasoning


# --- AIEngine.explain integration -------------------------------------------


@pytest.mark.asyncio
async def test_explain_strips_inline_think_tag_from_content():
    engine = _engine()
    engine.client = StubClient(
        {"content": "<think>internal deliberation</think>A clean, plain-English answer."}
    )

    written = await engine.explain(_variant())

    assert "internal deliberation" not in written.text
    assert "A clean, plain-English answer." in written.text
    assert written.model == engine.credit


@pytest.mark.asyncio
async def test_explain_strips_separate_reasoning_content_field():
    engine = _engine()
    engine.client = StubClient(
        {"content": "A clean, plain-English answer.", "reasoning_content": "internal deliberation"}
    )

    written = await engine.explain(_variant())

    assert "internal deliberation" not in written.text
    assert "A clean, plain-English answer." in written.text


@pytest.mark.asyncio
async def test_explain_handles_unclosed_think_tag_as_no_answer():
    engine = _engine()
    engine.client = StubClient(
        {"content": "<think>ran out of tokens mid-thought and never closed"}
    )

    written = await engine.explain(_variant())

    assert written.model is None
    assert "ran out of tokens mid-thought" not in written.text
    assert "increase max output tokens" in (written.error or "")


@pytest.mark.asyncio
async def test_explain_handles_only_reasoning_no_answer():
    engine = _engine()
    engine.client = StubClient({"content": "", "reasoning_content": "thinking forever"})

    written = await engine.explain(_variant())

    assert written.model is None
    assert "thinking forever" not in written.text
    assert "increase max output tokens" in (written.error or "")


@pytest.mark.asyncio
async def test_safety_gate_ignores_diagnostic_language_in_reasoning():
    """The sharpest case: a diagnostic phrase in the *reasoning* must not flag."""
    engine = _engine()
    engine.client = StubClient(
        {
            "content": "This variant is a well-studied risk factor worth discussing with a counselor.",
            "reasoning_content": "the user definitely has the disease and you have it for certain",
        }
    )

    written = await engine.explain(_variant())

    assert "Safety Note" not in written.text
    assert "definitely has the disease" not in written.text


@pytest.mark.asyncio
async def test_safety_gate_still_catches_diagnostic_language_in_the_answer():
    """The reverse: the same phrase in the *answer* must still trip the gate."""
    engine = _engine()
    engine.client = StubClient(
        {
            "content": "You definitely have the disease and you will develop symptoms.",
            "reasoning_content": "this is a heuristic, findings are not certainties",
        }
    )

    written = await engine.explain(_variant())

    assert "Safety Note" in written.text
