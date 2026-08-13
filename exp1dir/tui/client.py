import httpx


class GatewayClient:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self._http = httpx.Client(timeout=30.0)

    def health(self):
        return self._http.get(f"{self.base}/health").json()

    def models(self):
        return self._http.get(f"{self.base}/models").json()

    def set_model(self, name: str):
        r = self._http.post(f"{self.base}/models/active", json={"model": name})
        r.raise_for_status()
        return r.json()

    def start(self, task: str):
        return self._http.post(f"{self.base}/runs", json={"task": task}).json()["run_id"]

    def interrupt(self, run_id: str, note: str = ""):
        self._http.post(f"{self.base}/runs/{run_id}/interrupt", json={"note": note})

    def message(self, run_id: str, text: str):
        self._http.post(f"{self.base}/runs/{run_id}/message", json={"text": text})

    def memory(self):
        return self._http.get(f"{self.base}/memory").json()

    def skills(self):
        return self._http.get(f"{self.base}/skills").json()

    def history(self):
        return self._http.get(f"{self.base}/runs").json()

    def mcp(self):
        return self._http.get(f"{self.base}/mcp").json()

    def mcp_reload(self):
        r = self._http.post(f"{self.base}/mcp/reload")
        r.raise_for_status()
        return r.json()

    def mcp_enabled(self, name: str, enabled: bool):
        r = self._http.post(f"{self.base}/mcp/{name}/enabled", json={"enabled": enabled})
        r.raise_for_status()
        return r.json()
