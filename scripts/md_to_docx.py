"""
模块 35 · 把学习说明的 Markdown 转成 Word（给老师看）
--------------------------------------------------------------------
支持：# ~ #### 标题、表格、代码块、无序列表、加粗、行内代码、分隔线。
用法：python scripts/md_to_docx.py docs/学习与实践说明.md docs/学习与实践说明.docx
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

FONT_CN = "微软雅黑"
FONT_EN = "Calibri"
FONT_CODE = "Consolas"
BT = chr(96)                  # 反引号：Markdown 的行内代码标记
INLINE_RE = re.compile(r"(\*\*[^*]+\*\*|" + BT + r"[^" + BT + r"]+" + BT + ")")


def _set_font(run, name: str = FONT_EN, size: float | None = None, bold: bool = False) -> None:
    run.font.name = name
    run.font.bold = bold
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), FONT_CN)
    rfonts.set(qn("w:ascii"), name)
    rfonts.set(qn("w:hAnsi"), name)
    if size:
        run.font.size = Pt(size)


def _shade(paragraph, color: str = "F2F2F2") -> None:
    ppr = paragraph._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), color)
    ppr.append(shd)


def _add_inline(paragraph, text: str) -> None:
    """处理 **加粗** 与行内代码两种标记。"""
    for chunk in INLINE_RE.split(text):
        if not chunk:
            continue
        if chunk.startswith("**") and chunk.endswith("**"):
            _set_font(paragraph.add_run(chunk[2:-2]), bold=True)
        elif chunk.startswith(BT) and chunk.endswith(BT):
            run = paragraph.add_run(chunk[1:-1])
            _set_font(run, name=FONT_CODE, size=9.5)
            run.font.color.rgb = RGBColor(0xC7, 0x25, 0x4E)
        else:
            _set_font(paragraph.add_run(chunk))


def _add_table(doc, rows: list[list[str]]) -> None:
    if not rows:
        return
    cols = max(len(r) for r in rows)
    table = doc.add_table(rows=0, cols=cols)
    table.style = "Table Grid"
    for i, row in enumerate(rows):
        cells = table.add_row().cells
        for j in range(cols):
            text = row[j] if j < len(row) else ""
            para = cells[j].paragraphs[0]
            para.alignment = WD_ALIGN_PARAGRAPH.LEFT
            _add_inline(para, text)
            for run in para.runs:
                run.font.size = Pt(9.5)
                if i == 0:
                    run.font.bold = True
    doc.add_paragraph()


def convert(src: Path, dst: Path) -> int:
    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = FONT_EN
    normal.font.size = Pt(10.5)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), FONT_CN)

    lines = src.read_text(encoding="utf-8").split("\n")
    in_code = False
    code_buf: list[str] = []
    table_buf: list[list[str]] = []
    first_heading_done = False

    for line in lines:
        stripped = line.strip()

        if stripped.startswith(BT * 3):
            if in_code:
                para = doc.add_paragraph()
                _shade(para)
                for k, code_line in enumerate(code_buf):
                    run = para.add_run(code_line)
                    _set_font(run, name=FONT_CODE, size=9)
                    if k < len(code_buf) - 1:
                        run.add_break()
                doc.add_paragraph()
                code_buf = []
                in_code = False
            else:
                if table_buf:
                    _add_table(doc, table_buf)
                    table_buf = []
                in_code = True
            continue

        if in_code:
            code_buf.append(line)
            continue

        if stripped.startswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                continue
            table_buf.append(cells)
            continue
        if table_buf:
            _add_table(doc, table_buf)
            table_buf = []

        if stripped in ("---", "***", "___"):
            doc.add_paragraph()
            continue

        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            text = stripped[level:].strip()
            if level == 1 and not first_heading_done:
                h = doc.add_heading(level=0)
                _add_inline(h, text)
                for run in h.runs:
                    _set_font(run, size=20, bold=True)
                first_heading_done = True
            else:
                h = doc.add_heading(level=min(level - 1, 4))
                _add_inline(h, text)
                for run in h.runs:
                    _set_font(run, size={2: 15, 3: 12.5, 4: 11}.get(level, 11), bold=True)
                    run.font.color.rgb = RGBColor(0x1F, 0x3B, 0x73)
            continue

        if stripped.startswith(("- ", "* ")):
            para = doc.add_paragraph(style="List Bullet")
            _add_inline(para, stripped[2:])
            continue

        m = re.match(r"^\d+\.\s", stripped)
        if m:
            para = doc.add_paragraph(style="List Number")
            _add_inline(para, stripped[m.end():])
            continue

        if not stripped:
            continue

        _add_inline(doc.add_paragraph(), stripped)

    if table_buf:
        _add_table(doc, table_buf)
    doc.save(dst)
    return len(doc.paragraphs)


if __name__ == "__main__":
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    print("已生成：" + str(dst) + "，段落数：" + str(convert(src, dst)))
