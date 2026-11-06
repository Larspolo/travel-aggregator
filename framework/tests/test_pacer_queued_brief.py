"""A fire of the pacer makes a session with two queued turns: the stored prompt (no brief), then the brief. The first
turn finds the brief in the queue and ends at once, so the brief gets a fresh context (#4550, `tokens.queued_brief`)."""
import json

import pacer
import tokens

PROMPT = {"type": "queue-operation", "operation": "enqueue", "content": "/scheduled max lane deep"}
FIRE = {"type": "queue-operation", "operation": "enqueue",
        "content": f"<routine-fire-payload>\n    {pacer.HEAD}\n    ticket: 4550\n    claim: pacer-r1\n</routine-fire-payload>"}
TAKE = {"type": "queue-operation", "operation": "dequeue"}
TURN = {"type": "user", "message": {"content": "/scheduled max lane deep"}}


def test_the_first_turn_sees_the_brief_that_waits_behind_it():
    assert tokens.BRIEF == pacer.HEAD
    assert tokens.queued_brief([PROMPT, FIRE, TAKE, TURN]) == "ticket: 4550"
    assert tokens.queued_brief([PROMPT, FIRE, TAKE, TURN, TAKE]) is None       # the brief turn: nothing waits
    assert tokens.queued_brief([PROMPT, TAKE, TURN]) is None                    # a run with no brief
    assert tokens.queued_brief([PROMPT, FIRE, TAKE, {**FIRE, "operation": "remove"}]) is None


def test_the_option_exits_0_only_while_a_brief_waits(tmp_path, capsys):
    path = tmp_path / "s.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in (PROMPT, FIRE, TAKE, TURN)))
    assert tokens.main(["--queued", str(path)]) == 0
    assert "ticket: 4550" in capsys.readouterr().out
    path.write_text("".join(json.dumps(r) + "\n" for r in (PROMPT, FIRE, TAKE, TURN, TAKE)))
    assert tokens.main(["--queued", str(path)]) == 1
