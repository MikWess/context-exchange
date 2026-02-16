"""
Shared HTML utilities for the Context Exchange web pages.

Provides:
- LIGHT_THEME_CSS: clean, accessible CSS for public-facing pages
- markdown_to_html(): converts our markdown subset to HTML (no dependencies)
- wrap_page(): wraps content in a full HTML document with the light theme
"""
import re
from html import escape as html_escape


# ---------------------------------------------------------------------------
# Light theme CSS — clean, accessible, minimal
# ---------------------------------------------------------------------------
LIGHT_THEME_CSS = """
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
        background: #ffffff;
        color: #1a1a1a;
        line-height: 1.6;
        -webkit-font-smoothing: antialiased;
    }
    .container {
        max-width: 720px;
        margin: 0 auto;
        padding: 40px 24px;
    }
    h1 { font-size: 28px; font-weight: 700; margin-bottom: 8px; margin-top: 32px; }
    h2 { font-size: 22px; font-weight: 600; margin-bottom: 8px; margin-top: 28px; }
    h3 { font-size: 17px; font-weight: 600; margin-bottom: 6px; margin-top: 24px; }
    p { margin-bottom: 12px; }
    a { color: #2563eb; text-decoration: none; }
    a:hover { text-decoration: underline; }
    hr { border: none; border-top: 1px solid #e5e7eb; margin: 28px 0; }
    strong { font-weight: 600; }
    code {
        font-family: 'SF Mono', 'Menlo', 'Monaco', monospace;
        font-size: 13px;
        background: #f1f3f5;
        padding: 2px 6px;
        border-radius: 4px;
    }
    pre {
        background: #f1f3f5;
        padding: 16px;
        border-radius: 8px;
        overflow-x: auto;
        margin: 12px 0 16px;
        font-size: 13px;
        line-height: 1.5;
    }
    pre code {
        background: none;
        padding: 0;
    }
    ul, ol {
        margin: 8px 0 12px 24px;
    }
    li {
        margin-bottom: 4px;
    }
    table {
        width: 100%;
        border-collapse: collapse;
        margin: 12px 0 16px;
        font-size: 14px;
    }
    th {
        text-align: left;
        padding: 8px 12px;
        border-bottom: 2px solid #e5e7eb;
        font-weight: 600;
    }
    td {
        padding: 8px 12px;
        border-bottom: 1px solid #f1f3f5;
    }
    tr:last-child td {
        border-bottom: none;
    }
    .muted { color: #6b7280; font-size: 14px; }
"""


def wrap_docs_page(title, body_html, extra_css=""):
    """
    Wrap docs content in a full-width layout (no narrow container).

    Input: page title (str), body HTML with its own layout (str), optional extra CSS
    Output: complete HTML document (str)

    Unlike wrap_page(), this does NOT wrap content in a narrow .container div,
    so the body_html can implement its own 3-column grid layout.
    """
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{html_escape(title)}</title>
    <style>{LIGHT_THEME_CSS}{extra_css}</style>
</head>
<body>
    {body_html}
</body>
</html>"""


def wrap_page(title, body_html, extra_css=""):
    """
    Wrap HTML body content in a full document with the light theme.

    Input: page title (str), body HTML content (str), optional extra CSS
    Output: complete HTML document (str)
    """
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{html_escape(title)}</title>
    <style>{LIGHT_THEME_CSS}{extra_css}</style>
</head>
<body>
    <div class="container">
        {body_html}
    </div>
</body>
</html>"""


def markdown_to_html(md):
    """
    Convert a markdown string to HTML. Handles the subset we use in
    our setup instructions — no external dependencies.

    Input: markdown string
    Output: HTML string

    Supports: headers, bold, inline code, code blocks, tables,
    unordered lists, links, horizontal rules, paragraphs.
    """
    lines = md.split("\n")
    html_parts = []
    i = 0
    in_list = False

    while i < len(lines):
        line = lines[i]

        # --- Code blocks (```) ---
        if line.strip().startswith("```"):
            # Extract optional language hint (we ignore it for styling)
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(html_escape(lines[i]))
                i += 1
            html_parts.append(f"<pre><code>{chr(10).join(code_lines)}</code></pre>")
            i += 1
            continue

        # --- Horizontal rule ---
        if line.strip() == "---":
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append("<hr>")
            i += 1
            continue

        # --- Headers ---
        header_match = re.match(r"^(#{1,3})\s+(.+)$", line)
        if header_match:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            level = len(header_match.group(1))
            text = _inline_format(header_match.group(2))
            html_parts.append(f"<h{level}>{text}</h{level}>")
            i += 1
            continue

        # --- Table ---
        if "|" in line and i + 1 < len(lines) and re.match(r"^\s*\|[\s\-:|]+\|\s*$", lines[i + 1]):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            table_html = _parse_table(lines, i)
            html_parts.append(table_html[0])
            i = table_html[1]
            continue

        # --- Unordered list ---
        list_match = re.match(r"^(\s*)[*-]\s+(.+)$", line)
        if list_match:
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            text = _inline_format(list_match.group(2))
            html_parts.append(f"<li>{text}</li>")
            i += 1
            continue

        # --- End list if we hit a non-list line ---
        if in_list and not line.strip().startswith(("-", "*")):
            html_parts.append("</ul>")
            in_list = False

        # --- Blank line ---
        if not line.strip():
            i += 1
            continue

        # --- Paragraph (default) ---
        text = _inline_format(line)
        html_parts.append(f"<p>{text}</p>")
        i += 1

    # Close any open list
    if in_list:
        html_parts.append("</ul>")

    return "\n".join(html_parts)


def _inline_format(text):
    """
    Apply inline markdown formatting to a line of text.

    Handles: **bold**, `code`, [links](url)
    All user content is HTML-escaped first for safety.
    """
    # Escape HTML first (but preserve our markdown markers)
    # We need to be careful: escape first, then apply formatting
    text = html_escape(text)

    # Bold: **text** → <strong>text</strong>
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)

    # Inline code: `text` → <code>text</code>
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)

    # Links: [text](url) → <a href="url">text</a>
    text = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', text)

    return text


def _parse_table(lines, start):
    """
    Parse a markdown table starting at the given line index.

    Input: all lines, starting index (the header row)
    Output: (html_string, next_line_index)
    """
    parts = ["<table>"]

    # Header row
    header_cells = [c.strip() for c in lines[start].split("|") if c.strip()]
    parts.append("<thead><tr>")
    for cell in header_cells:
        parts.append(f"<th>{_inline_format(cell)}</th>")
    parts.append("</tr></thead>")

    # Skip separator row (|---|---|)
    i = start + 2

    # Body rows
    parts.append("<tbody>")
    while i < len(lines) and "|" in lines[i] and lines[i].strip():
        cells = [c.strip() for c in lines[i].split("|") if c.strip()]
        parts.append("<tr>")
        for cell in cells:
            parts.append(f"<td>{_inline_format(cell)}</td>")
        parts.append("</tr>")
        i += 1
    parts.append("</tbody></table>")

    return ("\n".join(parts), i)
