"""Tests for Markdown to HTML converter."""

import pytest

from naver_blog.converter import md_to_html


def test_title_extraction():
    md = "# My Title\n\nSome content here."
    title, html, images = md_to_html(md)
    assert title == "My Title"
    assert "My Title" not in html
    assert "Some content here" in html


def test_no_title():
    md = "Some content without a heading."
    title, html, images = md_to_html(md)
    assert title == ""
    assert "Some content" in html


def test_h2_not_treated_as_title():
    md = "## Subtitle\n\nContent."
    title, html, images = md_to_html(md)
    assert title == ""
    assert "Subtitle" in html


def test_image_extraction(tmp_path):
    md = "# Title\n\n![alt](images/photo.png)\n\n![web](https://example.com/img.png)"
    title, html, images = md_to_html(md, base_dir=str(tmp_path))
    assert len(images) == 1
    assert "images/photo.png" in images[0]


def test_table_styling():
    md = "# Title\n\n| A | B |\n|---|---|\n| 1 | 2 |"
    title, html, images = md_to_html(md)
    assert "border-collapse" in html
    assert "border: 1px solid" in html


def test_multiple_headings():
    md = "# Main Title\n\n## Section 1\n\nContent\n\n## Section 2\n\nMore content"
    title, html, images = md_to_html(md)
    assert title == "Main Title"
    assert "Section 1" in html
    assert "Section 2" in html


def test_fenced_code_block():
    md = "# Title\n\n```python\nprint('hello')\n```"
    title, html, images = md_to_html(md)
    assert "print" in html
