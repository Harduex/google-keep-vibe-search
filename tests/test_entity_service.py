"""Tests for entity resolution service."""

import os

os.environ.setdefault("ENABLE_IMAGE_SEARCH", "false")
os.environ.setdefault("ENABLE_ENTITY_RESOLUTION", "false")

import json
import pytest
from unittest.mock import MagicMock, patch


class MockDoc:
    """Mock spaCy Doc with entities."""

    def __init__(self, entities):
        self.ents = [MockEntity(text, label) for text, label in entities]


class MockEntity:
    """Mock spaCy entity."""

    def __init__(self, text, label_):
        self.text = text
        self.label_ = label_


class MockNLP:
    """Mock spaCy NLP pipeline."""

    def __init__(self, entity_map=None):
        self.entity_map = entity_map or {}

    def __call__(self, text):
        # Return entities based on text content
        entities = self.entity_map.get(text[:100], [])
        return MockDoc(entities)


class TestEntityExtraction:
    def test_extract_entities_finds_persons(self):
        from app.services.entity_service import EntityService

        svc = EntityService.__new__(EntityService)
        svc.nlp = MockNLP({
            "Meeting Notes Discussion with John Smith about project": [("John Smith", "PERSON")],
        })

        notes = [{"id": "n1", "title": "Meeting Notes", "content": "Discussion with John Smith about project"}]
        result = svc._extract_entities(notes)
        assert "n1" in result
        assert ("John Smith", "PERSON") in result["n1"]

    def test_extract_entities_filters_labels(self):
        from app.services.entity_service import EntityService

        svc = EntityService.__new__(EntityService)
        svc.nlp = MockNLP({
            " Note content": [("Monday", "DATE"), ("Google", "ORG")],
        })

        notes = [{"id": "n1", "title": "", "content": "Note content"}]
        result = svc._extract_entities(notes)
        # DATE should be filtered out, ORG kept
        assert "n1" in result
        entities = [e[0] for e in result["n1"]]
        assert "Google" in entities
        assert "Monday" not in entities

    def test_extract_entities_empty_notes(self):
        from app.services.entity_service import EntityService

        svc = EntityService.__new__(EntityService)
        svc.nlp = MockNLP()

        result = svc._extract_entities([])
        assert result == {}


class TestEntityClustering:
    def test_cluster_similar_names(self):
        from app.services.entity_service import EntityService

        svc = EntityService.__new__(EntityService)
        svc.entity_index = {}
        svc.alias_map = {}

        raw = {
            "n1": [("John Smith", "PERSON")],
            "n2": [("John Smth", "PERSON")],  # typo, but Jaro-Winkler should match
            "n3": [("Paris", "GPE")],
        }
        svc._cluster_entities(raw)

        # John Smith and John Smth should be clustered
        assert svc.alias_map.get("john smith") == svc.alias_map.get("john smth")
        # Paris should be separate
        assert "paris" in svc.alias_map

    def test_cluster_different_names_not_merged(self):
        from app.services.entity_service import EntityService

        svc = EntityService.__new__(EntityService)
        svc.entity_index = {}
        svc.alias_map = {}

        raw = {
            "n1": [("Alice", "PERSON")],
            "n2": [("Bob", "PERSON")],
        }
        svc._cluster_entities(raw)

        # Different names should not be clustered
        assert svc.alias_map.get("alice") != svc.alias_map.get("bob")


class TestEntityQuery:
    def test_extract_from_query_finds_known_entity(self):
        from app.services.entity_service import EntityService

        svc = EntityService.__new__(EntityService)
        svc.nlp = MockNLP({"Tell me about Paris": [("Paris", "GPE")]})
        svc.alias_map = {"paris": "Paris"}

        result = svc.extract_from_query("Tell me about Paris")
        assert "Paris" in result

    def test_extract_from_query_unknown_entity(self):
        from app.services.entity_service import EntityService

        svc = EntityService.__new__(EntityService)
        svc.nlp = MockNLP({"Something about XYZ": [("XYZ", "ORG")]})
        svc.alias_map = {}

        result = svc.extract_from_query("Something about XYZ")
        assert result == []

    def test_find_notes_returns_matching_ids(self):
        from app.services.entity_service import EntityService

        svc = EntityService.__new__(EntityService)
        svc.entity_index = {
            "Paris": {"n1", "n3"},
            "Google": {"n2"},
        }

        result = svc.find_notes(["Paris"])
        assert result == {"n1", "n3"}

    def test_find_notes_multiple_entities(self):
        from app.services.entity_service import EntityService

        svc = EntityService.__new__(EntityService)
        svc.entity_index = {
            "Paris": {"n1"},
            "Google": {"n2"},
        }

        result = svc.find_notes(["Paris", "Google"])
        assert result == {"n1", "n2"}

    def test_get_entity_signal(self):
        from app.services.entity_service import EntityService

        svc = EntityService.__new__(EntityService)
        svc.nlp = MockNLP({"Notes about Paris": [("Paris", "GPE")]})
        svc.alias_map = {"paris": "Paris"}
        svc.entity_index = {"Paris": {"n1", "n3"}}

        signal = svc.get_entity_signal("Notes about Paris")
        note_ids = {nid for nid, _ in signal}
        assert note_ids == {"n1", "n3"}
        assert all(score == 1.0 for _, score in signal)


class TestEntityCache:
    def test_cache_roundtrip(self, tmp_path):
        from app.services.entity_service import EntityService

        svc = EntityService.__new__(EntityService)
        svc.entity_index = {"Paris": {"n1", "n3"}, "Google": {"n2"}}
        svc.alias_map = {"paris": "Paris", "google": "Google"}
        svc.cache_dir = str(tmp_path)

        cache_file = os.path.join(str(tmp_path), "entity_index.json")
        svc._save_to_cache(cache_file, "testhash")

        # Load into fresh instance
        svc2 = EntityService.__new__(EntityService)
        svc2._load_from_cache(cache_file)

        assert svc2.entity_index == {"Paris": {"n1", "n3"}, "Google": {"n2"}}
        assert svc2.alias_map == {"paris": "Paris", "google": "Google"}

    def test_cache_validity(self, tmp_path):
        from app.services.entity_service import EntityService

        svc = EntityService.__new__(EntityService)
        svc.entity_index = {}
        svc.alias_map = {}
        svc.cache_dir = str(tmp_path)

        cache_file = os.path.join(str(tmp_path), "entity_index.json")
        svc._save_to_cache(cache_file, "hash123")

        assert svc._is_cache_valid(cache_file, "hash123") is True
        assert svc._is_cache_valid(cache_file, "different") is False
