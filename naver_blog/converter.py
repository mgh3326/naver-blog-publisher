"""Markdown to HTML conversion with image extraction."""

import re
from pathlib import Path

import markdown


def md_to_html(md_content: str, base_dir: str = ".") -> tuple[str, str, list[str]]:
    """Convert Markdown content to HTML.

    Args:
        md_content: Raw Markdown string.
        base_dir: Base directory for resolving relative image paths.

    Returns:
        (title, html, images) where:
        - title: extracted from the first # heading
        - html: converted HTML body (without the title heading)
        - images: list of local image file paths found in the document
    """
    lines = md_content.strip().split("\n")

    # Extract title from first # heading
    title = ""
    title_line_idx = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("##"):
            title = stripped[2:].strip()
            title_line_idx = i
            break

    # Remove title line from content
    if title_line_idx is not None:
        content_lines = lines[:title_line_idx] + lines[title_line_idx + 1 :]
    else:
        content_lines = lines

    body_md = "\n".join(content_lines).strip()

    # Convert to HTML with extensions
    html = markdown.markdown(
        body_md,
        extensions=["tables", "fenced_code", "codehilite", "nl2br"],
    )

    # Apply table styling
    html = html.replace(
        "<table>",
        '<table style="border-collapse: collapse; width: 100%;">',
    )
    html = re.sub(
        r"<(td|th)>",
        r'<\1 style="border: 1px solid #ddd; padding: 8px;">',
        html,
    )

    # Extract local image paths
    images = []
    for match in re.finditer(r"!\[.*?\]\((.+?)\)", md_content):
        img_path = match.group(1)
        # Skip URLs
        if img_path.startswith(("http://", "https://", "//")):
            continue
        resolved = Path(base_dir) / img_path
        images.append(str(resolved))

    return title, html, images
