from typing import TypedDict


class AgentState(TypedDict):
    task: str
    run_id: str
    messages: list
    memory_snapshot: str
    skill_index: list
    loaded_skills: list
    cycle: int
    max_cycles: int
    pending_tool_calls: list
    pending_observations: list
    last_observation: str
    status: str
    final_answer: str
    reflection: str
    memory_writes: list
    active_model: str
