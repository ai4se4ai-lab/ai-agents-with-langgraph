from __future__ import annotations
import asyncio
import inspect
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import timedelta
from backend.tools.mcp_config import ServerSpec


def connection_for_spec(spec: ServerSpec) -> dict:
    if spec.transport == "stdio":
        return {
            "transport": "stdio",
            "command": spec.command,
            "args": spec.args,
            "env": spec.env,
        }
    return {
        "transport": "streamable_http",
        "url": spec.url,
        "headers": spec.headers,
        "timeout": timedelta(seconds=spec.timeout),
    }


def connect_server(spec: ServerSpec) -> list[dict]:
    from langchain_mcp_adapters.client import MultiServerMCPClient

    async def _list():
        client = MultiServerMCPClient({spec.name: connection_for_spec(spec)})
        tools = await client.get_tools(server_name=spec.name)
        out = []
        for t in tools:
            def make(tool=t):
                def fn(**kwargs):
                    def call():
                        ainvoke = getattr(tool, "ainvoke", None)
                        if ainvoke is not None:
                            return asyncio.run(ainvoke(kwargs))
                        return tool.invoke(kwargs)
                    pool = ThreadPoolExecutor(max_workers=1)
                    fut = pool.submit(call)
                    try:
                        result = fut.result(timeout=spec.timeout)
                    except FutureTimeout:
                        raise TimeoutError(f"MCP {spec.name}/{tool.name} timed out after {spec.timeout}s")
                    finally:
                        pool.shutdown(wait=False, cancel_futures=True)
                    return str(result)
                fn.__doc__ = getattr(tool, "description", None) or tool.name
                fn.__name__ = tool.name
                fn.args_schema = getattr(tool, "args_schema", None)
                src = getattr(tool, "func", None) or getattr(tool, "coroutine", None)
                if src is not None:
                    try:
                        fn.__signature__ = inspect.signature(src)
                    except (TypeError, ValueError):
                        pass
                return fn
            out.append({"name": t.name, "fn": make(), "description": getattr(t, "description", "") or t.name})
        return out

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_list())
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_list())
    finally:
        loop.close()
