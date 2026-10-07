from lighthouse_gc.core.text import plural


def test_plural():
    assert plural(1, "candidate") == "1 candidate"
    assert plural(12, "candidate") == "12 candidates"
    assert plural(0, "signal") == "0 signals"
    assert plural(1, "criterion") == "1 criterion" and plural(3, "more criterion") == "3 more criteria"
    assert plural(2, "match") == "2 matches" and plural(2, "metric row") == "2 metric rows"
    assert plural(1200, "token") == "1,200 tokens" and plural(2, "person", "people") == "2 people"
