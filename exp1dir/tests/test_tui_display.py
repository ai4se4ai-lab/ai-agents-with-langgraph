from tui.display import classify_step, event_body, split_events


def test_task_and_success_stay_visible_other_steps_are_thinking():
    events = [
        {"step": "task", "text": "what is my name?"},
        {"step": "reason", "text": "thinking"},
        {"step": "act", "input": '{"action": "read"}'},
        {"step": "observe", "observation": "ERROR: unknown action read"},
        {"step": "learn", "text": "{}"},
        {"step": "memory_update", "text": "none"},
        {"step": "success", "text": "Your name is Majid Babaei."},
    ]
    buckets = split_events(events)
    assert [e["step"] for e in buckets["task"]] == ["task"]
    assert [e["step"] for e in buckets["final"]] == ["success"]
    assert [e["step"] for e in buckets["thinking"]] == [
        "reason",
        "act",
        "observe",
        "learn",
        "memory_update",
    ]


def test_classify_step():
    assert classify_step("task") == "task"
    assert classify_step("success") == "final"
    assert classify_step("reason") == "thinking"
    assert classify_step("error") == "thinking"


def test_event_body_prefers_text_then_observation_then_input():
    assert event_body({"text": "hi"}) == "hi"
    assert event_body({"observation": "saw it"}) == "saw it"
    assert event_body({"input": "{}"}) == "{}"
    assert event_body({}) == ""
