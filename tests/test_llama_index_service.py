"""Tests for app.services.llama_index_service."""

import pytest
from unittest.mock import MagicMock, patch


class FakeSettings:
    """Minimal settings stub for LlamaIndexService tests."""

    llm_api_base_url = ""
    ollama_api_url = "http://localhost:11434"
    llm_api_key = ""
    llm_model = "test-model"

    @property
    def resolved_api_base_url(self):
        if self.llm_api_base_url:
            return self.llm_api_base_url.rstrip("/") + "/"
        return f"{self.ollama_api_url}/v1/"


class TestLlamaIndexServiceInit:
    """Test LlamaIndexService initialisation and configuration."""

    def test_import_available(self):
        """The llama_index_service module should be importable."""
        from app.services.llama_index_service import LlamaIndexService
        assert LlamaIndexService is not None

    def test_embed_model_name_constant(self):
        from app.services.llama_index_service import LlamaIndexService
        assert LlamaIndexService.EMBED_MODEL_NAME == "all-MiniLM-L6-v2"

    def test_embed_dimension_constant(self):
        from app.services.llama_index_service import LlamaIndexService
        assert LlamaIndexService.EMBED_DIMENSION == 384

    @patch("app.services.llama_index_service._LLAMA_INDEX_AVAILABLE", False)
    def test_unavailable_when_imports_missing(self):
        from app.services.llama_index_service import LlamaIndexService
        service = LlamaIndexService(FakeSettings())
        assert service.available is False
        assert service.embed_model is None
        assert service.llm is None

    def test_embed_dimension_property(self):
        from app.services.llama_index_service import LlamaIndexService
        service = LlamaIndexService.__new__(LlamaIndexService)
        assert service.embed_dimension == 384


class TestLlamaIndexServiceWithMocks:
    """Test with mocked LlamaIndex dependencies."""

    @patch("app.services.llama_index_service.OpenAILike")
    @patch("app.services.llama_index_service.HuggingFaceEmbedding")
    @patch("app.services.llama_index_service.LlamaSettings")
    @patch("app.services.llama_index_service._LLAMA_INDEX_AVAILABLE", True)
    def test_init_with_defaults(self, mock_llama_settings, mock_hf, mock_openai):
        from app.services.llama_index_service import LlamaIndexService

        mock_embed = MagicMock()
        mock_hf.return_value = mock_embed
        mock_llm = MagicMock()
        mock_openai.return_value = mock_llm

        settings = FakeSettings()
        service = LlamaIndexService(settings)

        assert service.available is True
        assert service.embed_model is mock_embed
        assert service.llm is mock_llm

        # Verify HuggingFace embedding was initialised with correct model
        mock_hf.assert_called_once_with(model_name="all-MiniLM-L6-v2")

        # Verify OpenAILike was called with derived base URL
        mock_openai.assert_called_once_with(
            api_base="http://localhost:11434/v1/",
            api_key="not-needed",
            model="test-model",
            is_chat_model=True,
        )

        # Verify global settings were updated
        assert mock_llama_settings.embed_model == mock_embed
        assert mock_llama_settings.llm == mock_llm

    @patch("app.services.llama_index_service.OpenAILike")
    @patch("app.services.llama_index_service.HuggingFaceEmbedding")
    @patch("app.services.llama_index_service.LlamaSettings")
    @patch("app.services.llama_index_service._LLAMA_INDEX_AVAILABLE", True)
    def test_custom_api_base_url(self, mock_llama_settings, mock_hf, mock_openai):
        from app.services.llama_index_service import LlamaIndexService

        settings = FakeSettings()
        settings.llm_api_base_url = "http://custom:8080/v1"
        settings.llm_api_key = "test-key"

        LlamaIndexService(settings)

        mock_openai.assert_called_once_with(
            api_base="http://custom:8080/v1/",
            api_key="test-key",
            model="test-model",
            is_chat_model=True,
        )
