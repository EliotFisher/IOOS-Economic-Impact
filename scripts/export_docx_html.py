"""Export the MARACOOS Word brief as a self-contained, browser-friendly HTML file."""

from __future__ import annotations

import base64
import html
import sys
from pathlib import Path

from docx import Document
from docx.document import Document as DocumentType
from docx.oxml.ns import qn
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph


def iter_blocks(parent):
    parent_element = parent.element.body if isinstance(parent, DocumentType) else parent._tc
    for child in parent_element.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, parent)
        elif child.tag == qn("w:tbl"):
            yield Table(child, parent)


def paragraph_html(paragraph: Paragraph, document: DocumentType) -> str:
    parts: list[str] = []
    for run in paragraph.runs:
        text = html.escape(run.text).replace("\n", "<br>")
        for drawing in run._element.xpath(".//a:blip"):
            rel_id = drawing.get(qn("r:embed"))
            if rel_id and rel_id in document.part.rels:
                part = document.part.rels[rel_id].target_part
                mime = part.content_type or "image/png"
                data = base64.b64encode(part.blob).decode("ascii")
                text += f'<img src="data:{mime};base64,{data}" alt="MARACOOS regional observing coverage">'
        styles = []
        if run.bold:
            styles.append("font-weight:700")
        if run.italic:
            styles.append("font-style:italic")
        if run.font.size:
            styles.append(f"font-size:{run.font.size.pt:.2f}pt")
        if run.font.color and run.font.color.rgb:
            styles.append(f"color:#{run.font.color.rgb}")
        parts.append(f'<span style="{";".join(styles)}">{text}</span>' if styles else text)

    style_name = (paragraph.style.name if paragraph.style else "").lower()
    if "heading" in style_name:
        tag = "h2"
    elif "list" in style_name:
        tag = "li"
    else:
        tag = "p"
    align = paragraph.alignment
    align_css = {1: "center", 2: "right", 3: "justify"}.get(int(align) if align is not None else -1, "left")
    classes = "page-break" if paragraph._p.xpath(".//w:br[@w:type='page']") else ""
    return f'<{tag} class="{classes}" style="text-align:{align_css}">{"".join(parts)}</{tag}>'


def cell_shading(cell: _Cell) -> str:
    fills = cell._tc.xpath("./w:tcPr/w:shd/@w:fill")
    return f"background:#{fills[0]}" if fills and fills[0] not in {"auto", "FFFFFF"} else ""


def table_html(table: Table, document: DocumentType) -> str:
    rows = []
    for row in table.rows:
        cells = []
        seen_cells: set[int] = set()
        for cell in row.cells:
            cell_id = id(cell._tc)
            if cell_id in seen_cells:
                continue
            seen_cells.add(cell_id)
            content = []
            for block in iter_blocks(cell):
                content.append(
                    paragraph_html(block, document)
                    if isinstance(block, Paragraph)
                    else table_html(block, document)
                )
            cells.append(f'<td style="{cell_shading(cell)}">{"".join(content)}</td>')
        rows.append(f'<tr>{"".join(cells)}</tr>')
    return f'<table>{"".join(rows)}</table>'


def export(source: Path, destination: Path) -> None:
    document = Document(source)
    body = []
    for block in iter_blocks(document):
        body.append(
            paragraph_html(block, document)
            if isinstance(block, Paragraph)
            else table_html(block, document)
        )

    title = "MARACOOS Congressional Brief"
    css = """
    :root{--navy:#123d52;--teal:#007c89;--ink:#1f2d35;--gray:#58666d;--line:#cfdde1}
    *{box-sizing:border-box}body{margin:0;background:#e9eef0;color:var(--ink);font-family:Arial,sans-serif}
    .document{width:min(100%,8.5in);margin:28px auto;background:white;padding:.43in .56in;box-shadow:0 10px 30px #123d5224}
    p,h2{margin:0 0 5px;line-height:1.08}h2{color:var(--navy);font-size:12.2pt;margin-top:8px}
    table{width:100%;border-collapse:separate;border-spacing:3px;margin:2px 0 5px;table-layout:fixed}
    td{padding:7px 9px;vertical-align:top;border-radius:2px}td p:last-child{margin-bottom:0}
    img{display:block;max-width:100%;height:auto;margin:0 auto}li{margin:0 0 2px 16px;line-height:1.05}
    .page-break{break-before:page;margin-top:.55in;padding-top:.2in;border-top:1px solid var(--line)}
    @media print{body{background:#fff}.document{width:auto;margin:0;box-shadow:none}.page-break{border:0;break-before:page}}
    @media(max-width:700px){.document{margin:0;padding:24px 16px}table,tbody,tr,td{display:block;width:100%}td{margin-bottom:4px}}
    """
    output = (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{title}</title><style>{css}</style></head><body>"
        f'<main class="document">{"".join(body)}</main></body></html>'
    )
    destination.write_text(output, encoding="utf-8")


if __name__ == "__main__":
    export(Path(sys.argv[1]), Path(sys.argv[2]))
