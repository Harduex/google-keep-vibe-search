import math

import pytest

from app.models.label import Label, LabelVocabulary
from app.services.categorization_service import CategorizationService


def test_sanitize_tag_name():
    # JSON input
    assert (
        CategorizationService._sanitize_tag_name('{"tag": "Home Renovation"}') == "Home Renovation"
    )

    # Quoted input
    assert CategorizationService._sanitize_tag_name('"Travel Plans"') == "Travel Plans"

    # 4+ word input truncates to 3
    assert (
        CategorizationService._sanitize_tag_name("My Awesome Travel Plans Today")
        == "My Awesome Travel"
    )

    # Sentence input
    assert CategorizationService._sanitize_tag_name("These are some recipes.") == "These Are Some"

    # Cyrillic input is valid now
    assert CategorizationService._sanitize_tag_name("Рецепти") == "Рецепти"

    # Valid
    assert CategorizationService._sanitize_tag_name("Home Renovation") == "Home Renovation"


def test_apply_merge_map():
    vocab = LabelVocabulary()
    vocab.add(
        Label(
            name="Gym",
            seed_note_ids=["1", "2"],
            sample_notes=[{"title": "A"}],
            confidence=0.8,
            source="cluster",
            is_anchor=False,
        )
    )
    vocab.add(
        Label(
            name="Workout",
            seed_note_ids=["3"],
            sample_notes=[{"title": "B"}],
            confidence=0.6,
            source="cluster",
            is_anchor=False,
        )
    )
    vocab.add(
        Label(
            name="Recipes",
            seed_note_ids=["4"],
            sample_notes=[{"title": "C"}],
            confidence=0.9,
            source="cluster",
            is_anchor=False,
        )
    )

    merge_map = {
        "merges": [
            {"into": "Fitness", "from": ["Gym", "Workout"]},
            {"into": "Unknown", "from": ["DoesNotExist"]},
        ],
        "keep": ["Recipes"],
    }

    CategorizationService._apply_merge_map(vocab, merge_map)
    result = vocab.labels

    # Should have Fitness and Recipes
    assert len(result) == 2

    # Recipes preserved
    recipes = next((p for p in result if p.name == "Recipes"), None)
    assert recipes is not None
    assert recipes.seed_note_ids == ["4"]

    # Fitness merged
    fitness = next((p for p in result if p.name == "Fitness"), None)
    assert fitness is not None

    # Union of note_ids
    assert set(fitness.seed_note_ids) == {"1", "2", "3"}

    # Sample notes from largest constituent ("Gym" had count 2)
    assert fitness.sample_notes == [{"title": "A"}]

    # Weighted confidence: (0.8*2 + 0.6*1)/3 = 2.2/3 = 0.733... -> 0.73
    assert fitness.confidence == 0.73


def test_adaptive_sizing():
    # specific: max(8, int(math.log10(n) * 3))
    # broad: max(15, int(math.log10(n) * 6))

    # n = 100
    _, _, min_sz_spec, _ = CategorizationService._get_cluster_sizing("specific", 100)
    assert min_sz_spec == max(8, int(math.log10(100) * 3))  # max(8, 6) = 8

    _, _, min_sz_broad, _ = CategorizationService._get_cluster_sizing("broad", 100)
    assert min_sz_broad == max(15, int(math.log10(100) * 6))  # max(15, 12) = 15

    # n = 2000
    _, _, min_sz_spec, _ = CategorizationService._get_cluster_sizing("specific", 2000)
    assert min_sz_spec == max(8, int(math.log10(2000) * 3))  # int(3.3 * 3) = 9

    _, _, min_sz_broad, _ = CategorizationService._get_cluster_sizing("broad", 2000)
    assert min_sz_broad == max(15, int(math.log10(2000) * 6))  # int(3.3 * 6) = 19

    # n = 20000
    _, _, min_sz_spec, _ = CategorizationService._get_cluster_sizing("specific", 20000)
    assert min_sz_spec == max(8, int(math.log10(20000) * 3))  # int(4.3 * 3) = 12

    _, _, min_sz_broad, _ = CategorizationService._get_cluster_sizing("broad", 20000)
    assert min_sz_broad == max(15, int(math.log10(20000) * 6))  # int(4.3 * 6) = 25


def test_harvest_title_prefixes():
    import app.services.categorization_service as cat_mod

    # temporarily set threshold to 2 for test
    original = cat_mod.PREFIX_MIN_COUNT
    cat_mod.PREFIX_MIN_COUNT = 2

    try:
        notes = [
            {"title": "Tip: eat veggies"},
            {"title": "TIP: sleep well"},
            {"title": "Recipe - cake"},
            {"title": "recipe - pie"},
            {"title": "Just a normal title"},
            {"title": "10:30 meeting"},  # should not match
            {"title": "Рецепта: баница"},  # cyrillic
            {"title": "РЕЦЕПТА: мусака"},  # cyrillic
            {"title": "Aaa Bbb Ccc: three words prefix"},  # 3 words
            {"title": "Aaa Bbb Ccc Ddd: four words prefix"},  # should not match (max 3 words)
            {"title": "Aaa Bbb Ccc: another one"},
        ]

        result = CategorizationService._harvest_title_prefixes(notes)

        # Tip should be found (count 2)
        assert "tip" in result
        assert result["tip"] == 2

        # Recipe should be found (count 2)
        assert "recipe" in result
        assert result["recipe"] == 2

        # Рецепта should be found (count 2)
        assert "рецепта" in result
        assert result["рецепта"] == 2

        # Aaa Bbb Ccc should be found (count 2)
        assert "aaa bbb ccc" in result
        assert result["aaa bbb ccc"] == 2

        # 10:30 should NOT be found
        assert "10" not in result
        assert "10:30" not in result

    finally:
        cat_mod.PREFIX_MIN_COUNT = original


def test_tf_idf_keyword_extraction():
    # Test for Phase 10A: c-TF-IDF keyword extraction
    # We provide multiple clusters, and a generic word "use" should be penalized
    # while specific words should be surfaced.
    cluster1 = [
        {"title": "Workout notes", "content": "use dumbbells for curls"},
        {"title": "Gym plan", "content": "use bench press for chest"},
    ]
    cluster2 = [
        {"title": "Baking recipe", "content": "use flour and sugar"},
        {"title": "Cooking", "content": "use salt and pepper"},
    ]

    # We pass a list of clusters (list of lists of notes) to the new API
    # The current _get_hint_keywords expects a single list of notes, so this will fail
    # or complain about signature mismatch, fulfilling our "failing test" requirement.
    keywords_by_cluster = CategorizationService._get_hint_keywords(
        [cluster1, cluster2], max_words=2
    )

    # "use" is in every note across all clusters. With naive Counter, it would be the #1 word.
    # With TF-IDF, it should be heavily penalized (IDF goes to 0), surfacing the specific words instead.
    assert len(keywords_by_cluster) == 2
    assert "use" not in keywords_by_cluster[0]
    assert "use" not in keywords_by_cluster[1]

    # Cluster 1 specific words should include gym-related terms
    assert any(w in ["workout", "dumbbells", "bench", "gym"] for w in keywords_by_cluster[0])

    # Cluster 2 specific words should include cooking terms
    assert any(
        w in ["baking", "recipe", "flour", "sugar", "cooking"] for w in keywords_by_cluster[1]
    )
