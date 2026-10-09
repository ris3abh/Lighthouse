"""The review packet's reader-facing sentences (ADR 0020): a natural template per evidence type, the exhibit's quote
when no template fits, claim ids only as footnotes (full ids in matrix.csv only), and no unfilled or raw slot in
any line a reader sees. Everything here is invented."""

from __future__ import annotations

import csv
import importlib.util
import io
import re
import sys
import zipfile
from datetime import date
from pathlib import Path

import pytest
from pypdf import PdfReader

from areao1.criteria import packet, sentences
from areao1.criteria.sentences import Fact, problems, sentence

ROOT = Path(__file__).parents[1]


def _f(predicate, value, kind, excerpt, *, on=date(2024, 5, 20), org="", work=""):
    return Fact(person="Maya", full_name="Maya Chen", predicate=predicate, value=value, evidence_type=kind,
                exhibit="C1-01", excerpt=excerpt, on=on, org=org, work=work, captured=on)  # fmt: skip


SENTENCES = [
    (_f("award_received", "Northwind Engineering Excellence Award", "award_certificate",
        "Maya Chen received the Northwind Engineering Excellence Award on May 20, 2024."),
     "Maya received the Northwind Engineering Excellence Award in May 2024 (Exhibit C1-01)."),
    (_f("award_received", "Northwind Engineering Excellence Award", "award_certificate",
        "Maya Chen won the Northwind Engineering Excellence Award in 2024."),
     "Maya won the Northwind Engineering Excellence Award in 2024 (Exhibit C1-01)."),  # the source's verb
    (_f("judged_event", "Example Hackathon Series 2024 finals", "panel_letter",
        "Maya Chen served as a judge for the Example Hackathon Series 2024 finals on November 9, 2024."),
     "Maya served as a judge for the Example Hackathon Series 2024 finals (Exhibit C1-01)."),
    (_f("program_committee", "Example Systems Conf", "program_committee",
        "Maya Chen served on the program committee of Example Systems Conf in June 2025.", on=date(2025, 6, 2)),
     "Maya served on the program committee of Example Systems Conf in June 2025 (Exhibit C1-01)."),
    (_f("reviewer_for", "the Example Learning Symposium", "reviewer_record",
        "Maya Chen reviewed for the Example Learning Symposium."),
     "Maya reviewed for the Example Learning Symposium, as captured on May 20, 2024 (Exhibit C1-01)."),
    (_f("press_feature", "The engineer making queues boring again", "press_article",
        "Example Tech Weekly profiled Maya Chen in “The engineer making queues boring again” on February 11, 2025.",
        org="Example Tech Weekly", on=date(2025, 2, 11)),
     "Example Tech Weekly profiled Maya in “The engineer making queues boring again” in February 2025 (Exhibit C1-01)."),
    (_f("membership", "Example Engineering Society", "membership_certificate",
        "Maya Chen was elected to the Example Engineering Society in 2024."),
     "Maya was elected to the Example Engineering Society in 2024 (Exhibit C1-01)."),
    (_f("paper_published", "Queues at scale", "conference_paper",
        "Queues at scale, by Maya Chen, was published in 2024."),
     "Maya published “Queues at scale” in 2024 (Exhibit C1-01)."),
    (_f("adopted_by", "Harborview Robotics", "adoption_evidence",
        "Harborview Robotics adopted FastQueue for on-device inference.", work="FastQueue", on=date(2026, 2, 1)),
     "Harborview Robotics adopted FastQueue, as captured on February 1, 2026 (Exhibit C1-01)."),  # adopted, not uses
    (_f("adopted_by", "Acme Robotics", "adoption_evidence",
        "Acme Robotics runs FastQueue in production across its warehouse fleet.", work="FastQueue", on=date(2025, 9, 15)),
     "Acme Robotics runs FastQueue, as captured on September 15, 2025 (Exhibit C1-01)."),
    (_f("repo_stars", 4800, "open_source_project", "The FastQueue repository had 4,800 GitHub stars in September 2025.",
        work="FastQueue", on=date(2025, 9, 15)),
     "FastQueue had 4,800 GitHub stars in September 2025 (Exhibit C1-01)."),
    (_f("monthly_downloads", 120000, "adoption_evidence", "The FastQueue package was downloaded 120,000 times.",
        work="FastQueue", on=date(2026, 2, 28)),
     "FastQueue had 120,000 downloads a month, as captured on February 28, 2026 (Exhibit C1-01)."),
    (_f("role_title", "Tech lead", "role_letter", "Maya Chen held the role of Tech lead at Example Corp in 2024.",
        org="Example Corp"),
     "Maya held the role of Tech lead at Example Corp in 2024 (Exhibit C1-01)."),
    (_f("salary", "$310,000 a year", "pay_stub", "Maya Chen's base salary is $310,000 a year (2024)."),
     "Maya's compensation was $310,000 a year in 2024 (Exhibit C1-01)."),
    (_f("patent", "US Patent 12,345,678", "patent", "Maya Chen is a named inventor on US Patent 12,345,678."),
     "Maya is a named inventor on US Patent 12,345,678 (Exhibit C1-01)."),
]  # fmt: skip


@pytest.mark.parametrize(("fact", "expected"), SENTENCES)
def test_each_evidence_type_has_a_natural_sentence(fact, expected):
    assert sentence(fact) == expected
    assert problems(expected, (fact.predicate,)) == []


# The words a template adds of its own; everything else in a templated sentence must come from the quote.
GLUE = {"in", "the", "of", "for", "on", "as", "captured", "had", "a", "month", "week", "compensation", "was",
        "at", "exhibit", "an", "is", "stars", "github", "downloads", "citations", "readers"}  # fmt: skip
MONTHS = {d.strftime("%B").lower() for d in (date(2024, m, 1) for m in range(1, 13))}


def faithful(f: Fact, s: str) -> list[str]:
    """Words a templated sentence adds that its quote doesn't have (dates are checked separately: a date the quote
    doesn't state must read "as captured on")."""
    if s.startswith(f"Exhibit {f.exhibit} states:"):
        return []  # a quote is the source
    body = re.sub(r"\(Exhibit [^)]*\)\.$", "", s)
    stated = body.split(", as captured on ")[0]
    if ", as captured on " not in body:
        for y in re.findall(r"\b(?:19|20)\d\d\b", stated):
            assert y in f.excerpt, (s, "a year the quote doesn't state")
    quote = {w.lower() for w in re.findall(r"[\w’'$,.-]+", f.excerpt)}
    quote |= {w.rstrip(".,") for w in quote}
    extra = []
    for w in re.findall(r"[\w’'$,.-]+", stated):
        lw = w.lower().rstrip(".,")
        if (
            lw in quote
            or lw in GLUE
            or lw in MONTHS
            or lw.isdigit()
            or lw == f.person.lower()
            or lw == f"{f.person.lower()}'s"
        ):
            continue
        if any(q.startswith(lw[:6]) for q in quote if len(lw) > 5):  # downloads ~ downloaded
            continue
        extra.append(w)
    return extra


@pytest.mark.parametrize(("fact", "expected"), SENTENCES)
def test_no_template_changes_the_meaning_of_its_quote(fact, expected):
    assert faithful(fact, sentence(fact)) == [], sentence(fact)


@pytest.mark.parametrize(
    "fact",
    [
        _f(
            "adopted_by",
            "Acme Robotics",
            "adoption_evidence",
            "Acme Robotics evaluated FastQueue last year.",
            work="FastQueue",
        ),  # evaluated isn't adopted: no verb of the template, so it's quoted
        _f(
            "award_received", "Northwind Award", "award_certificate", "She received the Northwind Award."
        ),  # who?
        _f(
            "press_feature",
            "Queues",
            "press_article",
            "Maya Chen was profiled in “Queues”.",
            org="Example Weekly",
        ),
        _f("repo_stars", 4800, "open_source_project", "FastQueue is popular.", work="FastQueue"),  # no number
        _f(
            "award_received", "Northwind Award", "award_certificate", "Maya Chen received an award."
        ),  # no name
    ],
)
def test_when_the_quote_doesnt_say_it_that_way_it_is_quoted(fact):
    assert sentence(fact) == f"Exhibit C1-01 states: “{fact.excerpt}”"


@pytest.mark.parametrize(
    "fact",
    [
        _f(
            "award_received", 17, "award_certificate", excerpt="Won 17 engineering award."
        ),  # what the old demo had
        _f(
            "award_selectivity",
            "3 of 412 nominees",
            "award_certificate",
            excerpt="3 recipients from 412 nominees.",
        ),
        _f("teams_judged", "38 teams", "panel_letter", excerpt="The panel scored 38 finalist teams."),
        _f("award_received", "", "award_certificate", excerpt="Received the award."),
        _f("award_received", None, "award_certificate", excerpt="Received the award."),
        _f("judged_event", "hacks_2024", "panel_letter", excerpt="Judged Hacks 2024."),
        _f("repo_stars", 4800, "open_source_project", on=None, excerpt="4,800 stars."),
        _f("something_new", {"a": 1}, "media_mention", excerpt="A fact no template knows."),
    ],
)
def test_without_a_fitting_template_the_exhibit_is_quoted(fact):
    s = sentence(fact)
    assert s == f"Exhibit C1-01 states: “{fact.excerpt}”", s
    assert problems(s, (fact.predicate,)) == []


def test_no_template_and_value_leaves_a_slot_or_raw_token_or_changes_the_meaning():
    values = ["Example Award", "the Example Award", "", "17", 17, 0, 3.5, None, True, "x", "hacks_2024", "2024",
              "Award 2024", {"k": "v"}, ["a"], "$1,000", 4800]  # fmt: skip
    predicates = ("award_received", "judged_event", "program_committee", "reviewer_for", "press_feature", "membership",
                  "paper_published", "patent", "adopted_by", "created", "role_title", "salary", "repo_stars",
                  "monthly_downloads", "citation_count", "award_selectivity")  # fmt: skip
    for types, _, verbs, _ in sentences.NAMED:
        for kind in types:
            for predicate in predicates:
                for value in values:
                    shown = sentences.plain(value)
                    for excerpt in ("The document says so.",
                                    f"Maya Chen {verbs[0]} {shown} at Example Org, FastQueue, 4,800 GitHub stars, in 2024.",
                                    f"Example Org {verbs[-1]} FastQueue and {shown or 'more'}."):  # fmt: skip
                        for on in (date(2024, 1, 2), None):
                            for org in ("", "Example Org"):
                                f = Fact(person="Maya", full_name="Maya Chen", predicate=predicate, value=value,
                                         evidence_type=kind, exhibit="C2-03", excerpt=excerpt, on=on, org=org,
                                         work="FastQueue", captured=on)  # fmt: skip
                                s = sentence(f)
                                quoted = s.startswith(
                                    "Exhibit C2-03 states:"
                                )  # the source's own words, as they are
                                found = [
                                    x
                                    for x in problems(s, (predicate,))
                                    if not (quoted and x.startswith("snake"))
                                ]
                                assert found == [], (s, predicate, value, kind)
                                assert faithful(f, s) == [], (s, excerpt)
                                assert problems(sentences.label(f), ()) in ([], [f"snake_case {value}"]), (
                                    sentences.label(f)
                                )


def test_the_check_catches_what_the_old_template_wrote():
    old = "Maya Chen: award received 17, Exhibit C1-01. [clm_0a1b2c3d4e]"
    found = problems(old, ("award_received",))
    assert any(p.startswith("raw id") for p in found) and any("template predicate" in p for p in found)
    assert problems("received {value} in None", ()) and problems("judged hacks_2024", ())
    assert problems("Exhibit index ........ page 3", ()) == []  # a contents leader isn't a slot


# ------------------------------------------------------------------------------------------- the built packets


def _film(monkeypatch):
    spec = importlib.util.spec_from_file_location("film_demo", ROOT / "scripts" / "film_demo.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    from areao1.google import mail

    monkeypatch.setattr(mail, "IMAP", mail.IMAP)
    monkeypatch.setattr(mail, "SMTP", mail.SMTP)
    return mod


def _reader_lines(out: Path) -> list[str]:
    """Every line a reader sees: the review PDF's front matter, and the .docx body and footnotes."""
    reader = PdfReader(out / "packet.pdf")
    lines = []
    for page in reader.pages:
        text = page.extract_text()
        if text.startswith(("Exhibit C", "Fictional exhibit")) or "Fictional exhibit" in text:
            continue  # the exhibits themselves are the person's documents, shown as they are
        lines += text.splitlines()
    with zipfile.ZipFile(out / "packet.docx") as z:
        for part in ("word/document.xml", "word/footnotes.xml", "word/header1.xml"):
            xml = z.read(part).decode()
            for para in re.findall(r"<w:p>.*?</w:p>|<w:p .*?</w:p>", xml):
                text = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", para))
                if text.strip():
                    lines.append(text)
    return lines


def _check(ws, out: Path) -> list[str]:
    predicates = tuple({c.predicate for c in ws.memory.claims()})
    lines = _reader_lines(out)
    bad = [(line, problems(line.replace("&amp;", "&"), predicates)) for line in lines]
    bad = [b for b in bad if b[1]]
    assert not bad, bad[:10]
    assert not any("clm_" in line for line in lines)
    rows = list(csv.DictReader(io.StringIO((out / "matrix.csv").read_text())))
    assert rows and all(r["claim_id"].startswith("clm_") for r in rows)  # the full ids live here
    return lines


def test_mayas_packet_reads_naturally_with_footnotes(monkeypatch, tmp_path):
    from areao1.criteria.case import Case
    from areao1.vault.store import Vault

    film = _film(monkeypatch)
    film.build(tmp_path / "maya")
    ws = Case(tmp_path / "maya")
    m = packet.build(ws, Vault(ws))
    out = ws.root / "exports" / m["name"]
    lines = _check(ws, out)
    text = "\n".join(lines)
    assert "Maya received the Northwind Engineering Excellence Award in May 2024 (Exhibit C1-01)." in text
    assert "FastQueue had 4,800 GitHub stars in September 2025 (Exhibit C5-01)." in text
    assert "Exhibit C1-01 states: “The jury selected 3 recipients from 412 nominees.”" in text
    # grouped by exhibit, main fact first, figures, then supporting details (read in the Outline section)
    text = text[text.index("Drafted from approved claims only") :]
    head, main, detail = (text.index("Exhibit C1-01: Northwind Engineering Excellence Award"),
                          text.index("Maya received the Northwind"), text.index("Exhibit C1-01 states: “The jury"))  # fmt: skip
    assert head < main < detail
    assert text.index("Acme Robotics runs FastQueue") < text.index("FastQueue had 4,800 GitHub stars")
    c4 = [text.index(t) for t in ("Exhibit C4-01:", "Maya served as a judge for", "Exhibit C4-01 states:",
                                  "Exhibit C4-02:", "Maya served on the program committee", "Exhibit C4-02 states:")]  # fmt: skip
    assert c4 == sorted(c4), c4
    with zipfile.ZipFile(out / "packet.docx") as z:
        doc, notes = z.read("word/document.xml").decode(), z.read("word/footnotes.xml").decode()
    assert doc.count("<w:footnoteReference ") == m["claims"] == notes.count("<w:footnoteRef/>")
    assert "Exhibit C1-01, page 2 (packet page" in notes  # a footnote says where the quote is
    assert m["dropped_sentences"] == 0 and m["open_issues"] > 0


def test_ravis_packet_reads_naturally(monkeypatch, tmp_path):
    from areao1.vault.store import Vault

    _film(monkeypatch)
    sys.path.insert(0, str(ROOT / "scripts"))
    import demo_cases

    ws = demo_cases.build_persona("ravi", tmp_path / "ravi")
    m = packet.build(ws, Vault(ws))
    text = "\n".join(_check(ws, ws.root / "exports" / m["name"]))
    assert (
        "Ravi published “Calibrated Uncertainty in Vision-Language Models” in March 2024 (Exhibit C6-01)."
        in text
    )
    assert "Ravi reviewed for the Example Learning Symposium 2024 (Exhibit C4-01)." in text
    assert len(m["exhibits"]) == 7 and m["claims"] == 12
