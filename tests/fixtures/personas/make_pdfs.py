"""Write the three onboarding personas' LinkedIn-style PDFs (fictional people, deterministic bytes).

    .venv/bin/python tests/fixtures/personas/make_pdfs.py

The text follows the order pypdf extracts from a real LinkedIn "Save to PDF" export: the left column
(Contact, Top Skills, Languages, Certifications, Honors-Awards, Publications) first, then the name,
headline, location, Summary, Experience and Education. A tiny hand-written PDF writer keeps the fixtures
free of extra dependencies and byte-for-byte reproducible.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _escape(line: str) -> str:
    return line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write_pdf(path: Path, lines: list[str], title: str) -> None:
    per_page = 52
    pages = [lines[i : i + per_page] for i in range(0, len(lines), per_page)] or [[]]
    objects: list[bytes] = []

    def add(body: str | bytes) -> int:
        objects.append(body.encode("latin-1") if isinstance(body, str) else body)
        return len(objects)

    catalog = add("")  # placeholder, filled below
    pages_obj = add("")
    font = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    kids = []
    for chunk in pages:
        ops = ["BT", "/F1 10.5 Tf", "14 TL", "56 780 Td"]
        for line in chunk:
            ops.append(f"({_escape(line)}) '")
        ops.append("ET")
        stream = "\n".join(ops).encode("latin-1")
        content = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        kids.append(add(f"<< /Type /Page /Parent {pages_obj} 0 R /MediaBox [0 0 612 792] "
                        f"/Resources << /Font << /F1 {font} 0 R >> >> /Contents {content} 0 R >>"))  # fmt: skip
    objects[catalog - 1] = f"<< /Type /Catalog /Pages {pages_obj} 0 R >>".encode()
    objects[pages_obj - 1] = (
        f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>".encode()
    )
    info = add(f"<< /Title ({_escape(title)}) /Producer (LinkedIn) >>")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root {catalog} 0 R /Info {info} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))


def main() -> None:
    for folder in sorted(p.parent for p in HERE.glob("*/persona.json")):
        lines = (folder / "linkedin.txt").read_text(encoding="utf-8").splitlines()
        persona = json.loads((folder / "persona.json").read_text(encoding="utf-8"))
        write_pdf(folder / "linkedin.pdf", lines, f"{persona['name']} | LinkedIn")
        print("wrote", folder / "linkedin.pdf")


if __name__ == "__main__":
    main()
