"""The lexical safety filter over model explanations.

Pins two things: the labelled sentence set in tests/fixtures/safety_sentences.json
is fully caught (every unsafe sentence flagged, no safe sentence flagged), and
check_safety's notice/warning contract. The set is author-written and the
filter was tuned against it, so this is a regression guard on the filter's
intended scope, not evidence about how it fares on arbitrary model output.
"""

import json
from pathlib import Path

import pytest

from allelio.ai.safety import (
    SAFETY_CATEGORIES,
    check_safety,
    find_unsafe_language,
)

FIXTURE = Path(__file__).parent / "fixtures" / "safety_sentences.json"
DATA = json.loads(FIXTURE.read_text())


@pytest.mark.parametrize("item", DATA["unsafe"], ids=lambda i: i["text"][:50])
def test_every_unsafe_sentence_is_caught(item):
    matches = find_unsafe_language(item["text"])
    assert matches, f"not flagged: {item['text']!r}"
    assert item["category"] in {m.category for m in matches}, (
        f"flagged as {[m.category for m in matches]}, expected {item['category']}"
    )


@pytest.mark.parametrize("text", DATA["safe"], ids=lambda t: t[:50])
def test_no_safe_sentence_is_flagged(text):
    assert find_unsafe_language(text) == [], f"false positive: {text!r}"


def test_fixture_covers_every_category():
    assert {i["category"] for i in DATA["unsafe"]} == set(SAFETY_CATEGORIES)


def test_fixture_is_balanced_enough_to_mean_something():
    assert len(DATA["unsafe"]) >= 40 and len(DATA["safe"]) >= 40


class TestCheckSafety:
    def test_clean_text_passes_through_untouched(self):
        text = "You have one copy of the variant; carriers may have a modestly higher risk."
        cleaned, warnings = check_safety(text)
        assert cleaned == text and warnings == []

    def test_notice_names_the_category(self):
        cleaned, warnings = check_safety("You will develop the disease.")
        assert "Safety Note" in cleaned and "prognostic" in cleaned
        assert len(warnings) == 1 and "prognostic" in warnings[0]

    def test_one_warning_per_category_not_per_match(self):
        text = "You have the disease. You definitely have it. Stop taking warfarin."
        cleaned, warnings = check_safety(text)
        assert [w.split("(")[1].split(":")[0] for w in warnings] == ["diagnostic", "prescriptive"]
        assert "diagnostic, prescriptive" in cleaned

    def test_text_is_appended_to_not_rewritten(self):
        text = "You will get cancer."
        cleaned, _ = check_safety(text)
        assert cleaned.startswith(text)

    def test_empty_text(self):
        assert check_safety("") == ("", [])


class TestHedging:
    @pytest.mark.parametrize("text", [
        "You may have an increased risk.",
        "You will likely never notice this.",
        "This does not mean you have the condition.",
        "It is possible that you have a predisposition.",
        "If you have a family history, talk to a counselor.",
    ])
    def test_hedged_second_person_passes(self, text):
        assert find_unsafe_language(text) == []

    def test_hedge_in_an_earlier_sentence_does_not_excuse_a_later_one(self):
        text = "You may have a higher risk. You have the disease."
        matches = find_unsafe_language(text)
        assert {m.category for m in matches} == {"diagnostic"}
        assert all(m.start >= text.index("You have the") for m in matches)


class TestGenotypeFacts:
    @pytest.mark.parametrize("text", [
        "You have two copies of the risk allele.",
        "You have the AG genotype.",
        "You've got the common version.",
        "You have an increased risk of the condition.",
    ])
    def test_statements_about_the_data_pass(self, text):
        assert find_unsafe_language(text) == []
