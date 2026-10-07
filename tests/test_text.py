from areao1.core.text import plural


def test_plural():
    assert plural(1, "candidate") == "1 candidate"
    assert plural(12, "candidate") == "12 candidates"
    assert plural(0, "signal") == "0 signals"
    assert plural(1, "criterion") == "1 criterion" and plural(3, "more criterion") == "3 more criteria"
    assert plural(2, "match") == "2 matches" and plural(2, "metric row") == "2 metric rows"
    assert plural(1200, "token") == "1,200 tokens" and plural(2, "person", "people") == "2 people"


def test_names_person_needs_first_and_last_name_together():
    from areao1.core.text import names_person

    assert names_person("Judges: Maya Chen, Omar Haddad", ["Maya Chen"])
    assert names_person("Chen, Maya (Northwind)", ["Maya Chen"])
    assert names_person("Ravi K. Iyer gave the keynote", ["Ravi K. Iyer"])
    assert names_person("Ravi Iyer", ["Ravi Kumar Iyer", "Ravi Iyer"])  # an alias
    assert not names_person("Judges: M. Chen, Maya Lin", ["Maya Chen"])  # same names, different people
    assert not names_person("Chen won the award", ["Maya Chen"])
    assert not names_person("Maya Chen", ["Maya"])  # a single name is never enough
