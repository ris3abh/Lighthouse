"""The scoreboard cache (data/criteria.json) is rescored when the profile changes (labels, rules)."""

import json


def test_stale_scoreboard_is_rescored_after_a_profile_change(demo_ws):
    path = demo_ws.data_dir / "criteria.json"
    board = json.loads(path.read_text())
    board["rules_digest"] = "from-an-older-profile"
    for c in board["criteria"]:
        c["short_label"] = ""
    path.write_text(json.dumps(board))
    fresh = demo_ws.scoreboard()
    assert fresh.rules_digest != "from-an-older-profile"
    assert {c.id: c.short_label for c in fresh.criteria}["original_contributions"] == "Contributions"
    assert demo_ws.scoreboard().computed_at == fresh.computed_at  # cached again until the next change
