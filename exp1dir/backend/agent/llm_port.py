from dataclasses import dataclass, field


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)


class ScriptedLLM:
    def __init__(self, responses: list[LLMResponse]):
        self.responses = list(responses)
        self.i = 0

    def invoke(self, messages: list, tools: list) -> LLMResponse:
        if self.i >= len(self.responses):
            return LLMResponse(content="(script exhausted)", tool_calls=[])
        item = self.responses[self.i]
        self.i += 1
        return item


class OllamaLLM:
    def __init__(self, settings: dict, model: str | None = None):
        self.settings = settings
        self._model = model

    def _chat(self):
        from langchain_ollama import ChatOllama
        from backend.llm.ollama import list_models, resolve_active
        from backend.paths import HermesPaths

        paths = HermesPaths.default()
        tags = list_models(self.settings["ollama_base_url"], self.settings.get("ollama_api_key") or "")
        name = self._model or resolve_active(paths, tags, self.settings.get("ollama_model") or "")
        return ChatOllama(model=name, base_url=self.settings["ollama_base_url"])

    def invoke(self, messages: list, tools: list) -> LLMResponse:
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

        chat = self._chat()
        lc = []
        for m in messages:
            role = m.get("role")
            if role == "system":
                lc.append(SystemMessage(content=m["content"]))
            elif role == "user":
                lc.append(HumanMessage(content=m["content"]))
            elif role == "tool":
                lc.append(ToolMessage(content=m["content"], tool_call_id=m.get("tool_call_id") or "t"))
            else:
                raw_tcs = m.get("tool_calls") or []
                tcs = []
                for tc in raw_tcs:
                    if isinstance(tc, dict):
                        tcs.append(
                            {
                                "id": tc.get("id") or "t",
                                "name": tc.get("name"),
                                "args": tc.get("args") or {},
                                "type": "tool_call",
                            }
                        )
                    else:
                        tcs.append(
                            {
                                "id": getattr(tc, "id", None) or "t",
                                "name": getattr(tc, "name", None),
                                "args": getattr(tc, "args", None) or {},
                                "type": "tool_call",
                            }
                        )
                lc.append(AIMessage(content=m.get("content") or "", tool_calls=tcs))
        if tools:
            from backend.paths import HermesPaths
            from backend.tools.lc import bindable_tools
            paths = HermesPaths.default()
            if isinstance(tools, dict):
                chat = chat.bind_tools(bindable_tools(paths, tools))
            else:
                chat = chat.bind_tools(tools)
        msg = chat.invoke(lc)
        content = getattr(msg, "content", "") or ""
        tcs = []
        for tc in getattr(msg, "tool_calls", None) or []:
            tcs.append(ToolCall(id=tc.get("id") or "t", name=tc.get("name"), args=tc.get("args") or {}))
        return LLMResponse(content=content, tool_calls=tcs)
