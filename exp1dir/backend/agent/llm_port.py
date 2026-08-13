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
