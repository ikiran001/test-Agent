from __future__ import annotations

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


def adf_doc_from_sections(sections: list[tuple[str, str]]) -> dict[str, Any]:
    """Build Top-level ADF document with h2 sections and paragraphs / bullet lists."""
    content: list[dict[str, Any]] = []
    for title, body in sections:
        content.append(
            {
                "type": "heading",
                "attrs": {"level": 2},
                "content": [{"type": "text", "text": title}],
            }
        )
        body = (body or "").strip()
        if not body:
            continue
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
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": txt}],
                                }
                            ],
                        }
                    )
                    i += 1
                content.append({"type": "bulletList", "content": items})
                continue
            para_lines = []
            while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith("- "):
                para_lines.append(lines[i])
                i += 1
            text = " ".join(para_lines).strip()
            if text:
                content.append(
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": text}],
                    }
                )
    return {"type": "doc", "version": 1, "content": content}
