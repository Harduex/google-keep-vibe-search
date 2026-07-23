import hashlib
from pathlib import Path

ENV_EXAMPLE_SHA256 = "2f38a85c89635eb68020d9e675e32dda69f757ec7211c537e3c54ee7c22a7b0b"


def test_env_example_frozen():
    env_example_path = Path(__file__).parent.parent / ".env.example"
    assert env_example_path.exists(), ".env.example file not found"
    current_hash = hashlib.sha256(env_example_path.read_bytes()).hexdigest()
    assert current_hash == ENV_EXAMPLE_SHA256, "config is frozen — use constants.py"
