"""Build a self-contained HTML edition from rendered Word-document pages."""

from __future__ import annotations

import base64
import sys
from pathlib import Path


def export(destination: Path, page_paths: list[Path]) -> None:
    pages = []
    for index, page_path in enumerate(page_paths, start=1):
        encoded = base64.b64encode(page_path.read_bytes()).decode("ascii")
        pages.append(
            f'<img src="data:image/png;base64,{encoded}" '
            f'alt="MARACOOS Congressional Brief, page {index}">'
        )

    document = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>MARACOOS Congressional Brief</title>
  <style>
    * { box-sizing: border-box; }
    body { margin: 0; padding: 32px 16px; background: #e8eef0; }
    main { display: grid; gap: 28px; margin: 0 auto; max-width: 8.5in; }
    img { display: block; width: 100%; height: auto; background: white; box-shadow: 0 12px 32px rgba(18,61,82,.18); }
    @media (max-width: 640px) { body { padding: 12px 8px; } main { gap: 12px; } }
    @media print { body { padding: 0; background: white; } main { display: block; max-width: none; } img { box-shadow: none; break-after: page; } img:last-child { break-after: auto; } }
  </style>
</head>
<body><main>""" + "".join(pages) + """</main></body>
</html>
"""
    destination.write_text(document, encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit("Usage: export_docx_html.py OUTPUT.html PAGE-1.png [PAGE-2.png ...]")
    export(Path(sys.argv[1]), [Path(value) for value in sys.argv[2:]])
