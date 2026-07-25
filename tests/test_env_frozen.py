import hashlib
from pathlib import Path

ENV_EXAMPLE_SHA256 = "4d997cfab411fc4fc15ade682e05a97ae8cc97c2a1c6a80f6c94ca08141cb998"


def test_env_example_frozen():
    env_example_path = Path(__file__).parent.parent / ".env.example"
    assert env_example_path.exists(), ".env.example file not found"
    current_hash = hashlib.sha256(env_example_path.read_bytes()).hexdigest()
    assert current_hash == ENV_EXAMPLE_SHA256, "config is frozen — use constants.py"
