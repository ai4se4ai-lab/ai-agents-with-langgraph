import os
from dotenv import load_dotenv
from backend.paths import HermesPaths


def load_settings(paths: HermesPaths | None = None) -> dict:
    paths = paths or HermesPaths.default()
    load_dotenv(paths.root / ".env")
    return {
        "ollama_base_url": os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/"),
        "ollama_api_key": os.environ.get("OLLAMA_API_KEY", ""),
        "ollama_model": os.environ.get("OLLAMA_MODEL", ""),
        "gateway_host": os.environ.get("GATEWAY_HOST", "127.0.0.1"),
        "gateway_port": int(os.environ.get("GATEWAY_PORT", "8765")),
    }
