"""Tests for the merged naming path.

A second, PydanticAI-based ``tagging/naming.py`` was folded into
``CategorizationService``; it called an API that no longer existed. What
survived is the shipped tool-calling naming prompt with its retry ladder, plus
the ``_sanitize_tag_name`` helper. This file covers:

- the ``_sanitize_tag_name`` regression where a real LLM emitting
  ``Home_Improvement`` was silently dropped to ``""`` because the char-set
  rejected underscores; and
- the naming retry ladder's contract on success, empty response and total
  failure — without exercising the LLM network path.

The leak/privacy tests for the naming path live in
``test_categorization_service.py`` and are not duplicated here.
"""

import asyncio

import pytest

import app.services.categorization_service as cat_mod
from app.services.categorization_service import CategorizationService


async def _instant_sleep(*_args, **_kwargs):
    return None


# --------------------------------------------------------------------------
# _sanitize_tag_name — the underscore regression
# --------------------------------------------------------------------------


def test_sanitize_allows_underscore_tag():
    """`Home_Improvement` was once silently dropped to "".

    The char-set now permits underscores, so a real LLM that emits an
    underscore-joined tag survives sanitization instead of producing an
    unnamed cluster.
    """
    assert CategorizationService._sanitize_tag_name("Home_Improvement") == "Home_Improvement"


def test_sanitize_allows_multi_word_underscore_tag():
    assert CategorizationService._sanitize_tag_name("Machine_Learning") == "Machine_Learning"


def test_sanitize_still_rejects_pure_punctuation():
    # Sanitizer must not regress to letting junk through.
    assert CategorizationService._sanitize_tag_name("!!!") == ""
    assert CategorizationService._sanitize_tag_name("") == ""
    assert CategorizationService._sanitize_tag_name("   ") == ""


def test_sanitize_strips_punctuation_from_real_words():
    # Surrounding punctuation is stripped; the words survive.
    assert CategorizationService._sanitize_tag_name('"Travel Plans"') == "Travel Plans"
    assert CategorizationService._sanitize_tag_name("'Recipes!'") == "Recipes"


def test_sanitize_handles_json_wrapped_tag():
    assert (
        CategorizationService._sanitize_tag_name('{"tag": "Home Renovation"}') == "Home Renovation"
    )


def test_sanitize_handles_code_fence_wrapped_tag():
    fenced = '```\n{"tag": "Gardening Tips"}\n```'
    assert CategorizationService._sanitize_tag_name(fenced) == "Gardening Tips"


# --------------------------------------------------------------------------
# _sanitize_tag_name — the chatty-model regression
# --------------------------------------------------------------------------
#
# A model that answers in prose instead of calling the tool emits the JSON in a
# ```json fence and then keeps talking past the closing fence until it hits
# max_tokens. The fence unwrap used to require the text to both start AND end
# with ```, so the trailing chatter left the fence in place, `words[:3]` became
# "```Json Tag Music" and the leading-char check dropped the whole cluster name
# to "". Every one of these shapes carries an unambiguous tag and must survive.


def test_sanitize_handles_language_tagged_fence():
    assert (
        CategorizationService._sanitize_tag_name('```json\n{"tag": "Music Production"}\n```')
        == "Music Production"
    )


def test_sanitize_handles_fence_with_trailing_prose():
    """The exact shape observed from a chatty model, truncated at max_tokens."""
    raw = (
        '```json\n{"tag": "Music Production"}\n```' + "Okay, here is my reasoning: " + "blah " * 300
    )
    assert CategorizationService._sanitize_tag_name(raw) == "Music Production"


def test_sanitize_handles_bare_json_with_trailing_prose():
    raw = '{"tag": "Healthy Recipes"}\nI chose this because the notes are about food.'
    assert CategorizationService._sanitize_tag_name(raw) == "Healthy Recipes"


def test_sanitize_handles_prose_preamble_before_json():
    raw = 'Sure! Here is the tag you asked for:\n{"tag": "Bodybuilding"}'
    assert CategorizationService._sanitize_tag_name(raw) == "Bodybuilding"


def test_sanitize_handles_unfenced_prose_without_json():
    """No JSON to recover: fall through to the word path, not a silent "".

    A leading fence with no closing delimiter still unwraps.
    """
    assert CategorizationService._sanitize_tag_name("```\nGardening") == "Gardening"


def test_sanitize_rejects_prose_with_no_recoverable_tag():
    # Widening the JSON match must not turn junk into a tag.
    assert CategorizationService._sanitize_tag_name("```json\n{}\n```") == ""
    assert CategorizationService._sanitize_tag_name("```json\n\n```") == ""


def test_sanitize_truncates_to_three_words():
    assert CategorizationService._sanitize_tag_name("one two three four five") == "One Two Three"


def test_sanitize_allows_cyrillic():
    # The shipped pipeline supports Bulgarian notes; Cyrillic must round-trip.
    assert CategorizationService._sanitize_tag_name("Рецепти") == "Рецепти"


def test_sanitize_allows_ampersand_and_slash():
    assert CategorizationService._sanitize_tag_name("AT&T") == "At&T"
    assert CategorizationService._sanitize_tag_name("Tips/Tricks") == "Tips/Tricks"


# --------------------------------------------------------------------------
# _get_llm_tag_name — retry ladder contract
# --------------------------------------------------------------------------


class _ScriptedToolLLM:
    """LLM stub that returns a scripted sequence of tool-call responses.

    Each call to ``complete_with_tools`` pops the next scripted response.
    """

    def __init__(self, responses):
        self.responses = list(responses)
        self.call_count = 0

    async def complete_with_tools(self, *args, **kwargs):
        self.call_count += 1
        if self.responses:
            return self.responses.pop(0)
        return {"content": "", "tool_calls": []}

    async def complete(self, *args, **kwargs):
        self.call_count += 1
        return ""


def _tool_call_response(tag: str):
    class MockFunction:
        arguments = '{"tag": "%s"}' % tag

    class MockToolCall:
        function = MockFunction()

    return {"content": tag, "tool_calls": [MockToolCall()]}


@pytest.mark.asyncio
async def test_get_llm_tag_name_returns_sanitized_tag(monkeypatch):
    monkeypatch.setattr(cat_mod.asyncio, "sleep", _instant_sleep)

    llm = _ScriptedToolLLM([_tool_call_response("Home Renovation")])
    service = CategorizationService(search_service=None, note_service=None, llm=llm)

    result = await service._get_llm_tag_name(
        notes_text="unused by stub",
        keywords="renovation, home",
        neighbor_keywords="interior",
    )
    assert result == "Home Renovation"
    assert llm.call_count == 1


@pytest.mark.asyncio
async def test_get_llm_tag_name_retries_on_empty_then_succeeds(monkeypatch):
    """The retry ladder retries empty responses before giving up."""
    monkeypatch.setattr(cat_mod.asyncio, "sleep", _instant_sleep)

    llm = _ScriptedToolLLM(
        [
            {"content": "   ", "tool_calls": []},  # empty -> retry
            _tool_call_response("Gardening"),  # success on attempt 2
        ]
    )
    service = CategorizationService(search_service=None, note_service=None, llm=llm)

    result = await service._get_llm_tag_name(notes_text="x", keywords="x", neighbor_keywords="x")
    assert result == "Gardening"
    assert llm.call_count == 2


@pytest.mark.asyncio
async def test_get_llm_tag_name_returns_empty_after_max_retries(monkeypatch, tmp_path):
    """After 3 empty responses the ladder gives up and returns ""."""
    monkeypatch.setattr(cat_mod.asyncio, "sleep", _instant_sleep)
    # The failure log is written relative to CWD; isolate it to tmp_path so the
    # repo root never accumulates one (and we never read its contents here).
    monkeypatch.chdir(tmp_path)

    llm = _ScriptedToolLLM(
        [
            {"content": "", "tool_calls": []},
            {"content": "", "tool_calls": []},
            {"content": "", "tool_calls": []},
        ]
    )
    service = CategorizationService(search_service=None, note_service=None, llm=llm)

    result = await service._get_llm_tag_name(notes_text="x", keywords="x", neighbor_keywords="x")
    assert result == ""
    assert llm.call_count == 3


@pytest.mark.asyncio
async def test_get_llm_tag_name_passes_existing_tags_to_prompt(monkeypatch):
    """The vault's existing tags seed the prompt so the LLM reuses them.

    Captures the messages handed to the LLM (structural shape only — never
    dumped) and asserts an EXISTING TAGS section is present when the caller
    supplies tags. The prompt body itself is never inspected for note text.
    """
    monkeypatch.setattr(cat_mod.asyncio, "sleep", _instant_sleep)

    captured = {}

    class _CapturingLLM:
        call_count = 0

        async def complete_with_tools(self, *args, **kwargs):
            self.call_count += 1
            captured["messages"] = kwargs.get("messages", [])
            return _tool_call_response("Cooking")

        async def complete(self, *args, **kwargs):
            self.call_count += 1
            return ""

    service = CategorizationService(search_service=None, note_service=None, llm=_CapturingLLM())
    await service._get_llm_tag_name(
        notes_text="x",
        keywords="x",
        neighbor_keywords="x",
        existing_tags=["Cooking", "Travel", "Work"],
    )

    # The user message must carry the EXISTING TAGS marker the service appends.
    user_msgs = [m for m in captured["messages"] if m.get("role") == "user"]
    assert user_msgs, "no user message reached the LLM"
    assert "EXISTING TAGS" in user_msgs[-1]["content"]
    # And the supplied tags appear alongside the marker.
    assert "Cooking" in user_msgs[-1]["content"]
