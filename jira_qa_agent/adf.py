from __future__ import annotations

import re
from typing import Any


def plain_text_from_adf(node: dict[str, Any] | list[Any] | str | None) -> str:
    """Extract readable text from Jira ADF (comments / description)."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "\n".join(plain_text_from_adf(x) for x in node)
    if isinstance(node, dict):
        if node.get("text") is not None:
            return str(node["text"])
        parts: list[str] = []
        for child in node.get("content") or []:
            parts.append(plain_text_from_adf(child))
        return "\n".join(parts)
    return ""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _paragraph(text: str) -> dict[str, Any]:
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


def _cell(nodes: list[dict[str, Any]], is_header: bool = False) -> dict[str, Any]:
    return {"type": "tableHeader" if is_header else "tableCell", "attrs": {}, "content": nodes}


def _text_cell(text: str, is_header: bool = False) -> dict[str, Any]:
    text = (text or "").strip()
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()] or [text]
    return _cell([_paragraph(p) for p in paragraphs], is_header=is_header)


def _steps_cell(steps_text: str) -> dict[str, Any]:
    """Render numbered steps as an ADF ordered list inside a table cell."""
    steps_text = (steps_text or "").strip()
    lines = [l.strip() for l in steps_text.splitlines() if l.strip()]
    items = []
    for line in lines:
        clean = re.sub(r"^\d+\.\s*", "", line)
        items.append({"type": "listItem", "content": [_paragraph(clean)]})
    if not items:
        return _cell([_paragraph(steps_text)])
    return _cell([{"type": "orderedList", "content": items}])


def _render_body_nodes(body: str) -> list[dict[str, Any]]:
    """Convert a section body (plain text / bullet list) into ADF content nodes."""
    nodes: list[dict[str, Any]] = []
    body = (body or "").strip()
    if not body:
        return nodes
    lines = body.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            i += 1
            continue
        if line.strip().startswith("- "):
            items: list[dict[str, Any]] = []
            while i < len(lines) and lines[i].strip().startswith("- "):
                txt = lines[i].strip()[2:].strip()
                items.append(
                    {
                        "type": "listItem",
                        "content": [{"type": "paragraph", "content": [{"type": "text", "text": txt}]}],
                    }
                )
                i += 1
            nodes.append({"type": "bulletList", "content": items})
            continue
        para_lines = []
        while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith("- "):
            para_lines.append(lines[i])
            i += 1
        text = " ".join(para_lines).strip()
        if text:
            nodes.append({"type": "paragraph", "content": [{"type": "text", "text": text}]})
    return nodes


# ---------------------------------------------------------------------------
# Test case parser
# ---------------------------------------------------------------------------

def parse_test_cases_from_markdown(tc_section: str) -> list[dict[str, str]]:
    """Parse **TC-XX: Title** blocks from the Test Cases section."""
    cases: list[dict[str, str]] = []
    blocks = re.split(r"\n(?=\*\*TC-\d+:)", "\n" + tc_section.strip())
    for block in blocks:
        block = block.strip()
        if not block or not re.match(r"\*\*TC-\d+:", block):
            continue

        m = re.match(r"\*\*TC-(\d+):\s*(.*?)\*\*", block)
        if not m:
            continue

        tc: dict[str, str] = {
            "number": f"TC-{m.group(1).zfill(2)}",
            "title": m.group(2).strip(),
        }

        def _field(name: str) -> str:
            fm = re.search(
                rf"\*\*{re.escape(name)}:\*\*\s*(.*?)(?=\n-\s\*\*|\Z)",
                block,
                re.DOTALL,
            )
            return fm.group(1).strip() if fm else ""

        tc["type"] = _field("Type")
        tc["priority"] = _field("Priority")
        tc["description"] = _field("Description")
        tc["pre_condition"] = _field("Pre-condition")
        tc["steps"] = _field("Steps")
        tc["expected_result"] = _field("Expected Result")
        cases.append(tc)
    return cases


# ---------------------------------------------------------------------------
# ADF table from test cases
# ---------------------------------------------------------------------------

def adf_table_from_test_cases(cases: list[dict[str, str]]) -> dict[str, Any]:
    """Build a full-width ADF table node from parsed test cases."""
    headers = ["TC#", "Title", "Type", "Priority", "Description", "Pre-condition", "Steps", "Expected Result"]
    header_row: dict[str, Any] = {
        "type": "tableRow",
        "content": [_text_cell(h, is_header=True) for h in headers],
    }
    rows: list[dict[str, Any]] = [header_row]
    for tc in cases:
        rows.append({
            "type": "tableRow",
            "content": [
                _text_cell(tc.get("number", "")),
                _text_cell(tc.get("title", "")),
                _text_cell(tc.get("type", "")),
                _text_cell(tc.get("priority", "")),
                _text_cell(tc.get("description", "")),
                _text_cell(tc.get("pre_condition", "")),
                _steps_cell(tc.get("steps", "")),
                _text_cell(tc.get("expected_result", "")),
            ],
        })
    return {
        "type": "table",
        "attrs": {"isNumberColumnEnabled": False, "layout": "full-width"},
        "content": rows,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def adf_doc_from_report(sections: list[tuple[str, str]]) -> dict[str, Any]:
    """Build ADF document from report sections.

    The 'Test Cases' section is rendered as a table; all other sections use
    headings + paragraphs / bullet lists.
    """
    content: list[dict[str, Any]] = []
    for title, body in sections:
        content.append({
            "type": "heading",
            "attrs": {"level": 2},
            "content": [{"type": "text", "text": title}],
        })
        if title.strip().lower() == "test cases":
            cases = parse_test_cases_from_markdown(body)
            if cases:
                content.append(adf_table_from_test_cases(cases))
                continue
        content.extend(_render_body_nodes(body))
    return {"type": "doc", "version": 1, "content": content}


def adf_doc_from_sections(sections: list[tuple[str, str]]) -> dict[str, Any]:
    """Build ADF document from (title, body) tuples — all sections as text."""
    content: list[dict[str, Any]] = []
    for title, body in sections:
        content.append({
            "type": "heading",
            "attrs": {"level": 2},
            "content": [{"type": "text", "text": title}],
        })
        content.extend(_render_body_nodes(body))
    return {"type": "doc", "version": 1, "content": content}
