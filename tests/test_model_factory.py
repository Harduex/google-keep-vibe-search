from pydantic_ai.models.openai import OpenAIChatModel

from app.core.config import settings
from app.services.agent.model_factory import build_agent_model


def test_build_agent_model():
    model = build_agent_model()
    assert isinstance(model, OpenAIChatModel)
    assert model.model_name == settings.llm_model
