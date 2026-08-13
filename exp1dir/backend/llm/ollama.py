import json
import httpx
from backend.paths import HermesPaths


class ModelError(ValueError):
    pass


def list_models(base_url: str, api_key: str = "") -> list[str]:
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    resp = httpx.get(f"{base_url.rstrip('/')}/api/tags", headers=headers, timeout=10.0)
    resp.raise_for_status()
    models = resp.json().get("models") or []
    return [m.get("name") or m.get("model") for m in models if m.get("name") or m.get("model")]


def resolve_active(paths: HermesPaths, tags: list[str], env_model: str) -> str:
    if not tags:
        raise ModelError("no models available at OLLAMA_BASE_URL")
    cfg_model = ""
    if paths.config_file.exists():
        try:
            cfg_model = json.loads(paths.config_file.read_text(encoding="utf-8")).get("model") or ""
        except json.JSONDecodeError:
            cfg_model = ""
    if cfg_model in tags:
        return cfg_model
    if env_model in tags:
        return env_model
    return tags[0]


def set_active(paths: HermesPaths, name: str, tags: list[str]) -> str:
    if name not in tags:
        raise ModelError(f"unknown model: {name}")
    paths.home.mkdir(parents=True, exist_ok=True)
    data = {}
    if paths.config_file.exists():
        try:
            data = json.loads(paths.config_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    data["model"] = name
    paths.config_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return name
