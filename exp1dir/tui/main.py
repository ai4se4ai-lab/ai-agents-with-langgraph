import argparse
import socket
import subprocess
import sys
import time

from backend.paths import HermesPaths
from backend.settings import load_settings
from tui.app import HermesApp
from tui.client import GatewayClient


def _port_open(host: str, port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex((host, port)) == 0


def _is_gateway(host: str, port: int) -> bool:
    try:
        import httpx

        r = httpx.get(f"http://{host}:{port}/health", timeout=0.5)
        return r.status_code == 200
    except Exception:
        return False


def serve():
    import uvicorn

    from backend.agent.llm_port import OllamaLLM
    from backend.api.app import create_app

    paths = HermesPaths.default()
    settings = load_settings(paths)
    llm = OllamaLLM(settings)
    app = create_app(paths, llm, settings)
    uvicorn.run(app, host=settings["gateway_host"], port=settings["gateway_port"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("cmd", nargs="?", default="tui")
    args = parser.parse_args()
    if args.cmd == "serve":
        serve()
        return
    paths = HermesPaths.default()
    settings = load_settings(paths)
    host, port = settings["gateway_host"], settings["gateway_port"]
    if not _port_open(host, port):
        subprocess.Popen([sys.executable, "-m", "tui.main", "serve"], cwd=str(paths.root))
        for _ in range(50):
            if _is_gateway(host, port):
                break
            time.sleep(0.1)
    elif not _is_gateway(host, port):
        print(f"port {port} is occupied by a non-gateway process")
        sys.exit(1)
    HermesApp(GatewayClient(f"http://{host}:{port}")).run()


if __name__ == "__main__":
    main()
