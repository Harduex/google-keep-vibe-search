from app.services.tagging.dedupe import (
    DedupeReview,
    MergeDecision,
    adjudicate_gray_pairs,
    format_dashboard_proposals,
)


def test_adjudicate_gray_pairs_synthetic(monkeypatch):
    gray_pairs = [
        {"tag1": "recipes", "tag2": "cooking recipes", "similarity": 0.78, "count1": 10, "count2": 5},
        {"tag1": "guitar", "tag2": "music gear", "similarity": 0.65, "count1": 8, "count2": 15},
        {"tag1": "keyboard", "tag2": "mechanical keyboards", "similarity": 0.72, "count1": 12, "count2": 6},
    ]

    def stub_run_sync(prompt):
        class StubResult:
            data = DedupeReview(
                decisions=[
                    # True duplicate pair -> merge with valid canonical 'recipes'
                    MergeDecision(tag_a="recipes", tag_b="cooking recipes", verdict="merge", canonical="recipes"),
                    # Parent/child pair -> keep_both
                    MergeDecision(tag_a="guitar", tag_b="music gear", verdict="keep_both"),
                    # Hand-crafted invalid response -> hallucinated canonical 'piano' not in {'keyboard', 'mechanical keyboards'}
                    MergeDecision(tag_a="keyboard", tag_b="mechanical keyboards", verdict="merge", canonical="piano"),
                ]
            )

        return StubResult()

    class StubAgent:
        def __init__(self, model, result_type, retries):
            pass

        def run_sync(self, prompt):
            return stub_run_sync(prompt)

    monkeypatch.setattr("app.services.tagging.dedupe.Agent", StubAgent)

    decisions = adjudicate_gray_pairs(gray_pairs)

    assert len(decisions) == 3

    # Pair 1: true duplicate -> merge with valid canonical
    d1 = next(d for d in decisions if d.tag_a == "recipes" or d.tag_b == "recipes")
    assert d1.verdict == "merge"
    assert d1.canonical == "recipes"

    # Pair 2: parent/child -> keep_both
    d2 = next(d for d in decisions if d.tag_a == "guitar" or d.tag_b == "guitar")
    assert d2.verdict == "keep_both"

    # Pair 3: hallucinated canonical -> defaulted to keep_both without error
    d3 = next(d for d in decisions if d.tag_a == "keyboard" or d.tag_b == "keyboard")
    assert d3.verdict == "keep_both"
    assert d3.canonical is None or d3.canonical not in {"keyboard", "mechanical keyboards"}


def test_adjudicate_empty_gray_pairs_skips_llm():
    assert adjudicate_gray_pairs([]) == []


def test_format_dashboard_proposals():
    canonical_mapping = {"keyboards": "keyboard"}
    merge_decisions = [
        MergeDecision(tag_a="recipes", tag_b="cooking recipes", verdict="merge", canonical="recipes")
    ]
    tag_counts = {"recipes": 10, "cooking recipes": 5, "keyboard": 12, "keyboards": 4}

    proposals = format_dashboard_proposals(canonical_mapping, merge_decisions, tag_counts)
    assert len(proposals) == 2

    info_p = next(p for p in proposals if p["type"] == "info")
    assert "Auto-merged 'keyboards' into 'keyboard'" in info_p["message"]

    action_p = next(p for p in proposals if p["type"] == "proposal")
    assert action_p["action"] == "merge_tags"
    assert action_p["source_tag"] == "cooking recipes"
    assert action_p["target_tag"] == "recipes"
