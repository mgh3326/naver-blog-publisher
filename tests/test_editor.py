"""Tests for editor component helpers."""

import pytest

from naver_blog.editor import create_title_component, create_image_component


def test_create_title_component():
    comp = create_title_component("테스트 제목")
    assert comp["@ctype"] == "documentTitle"
    assert comp["title"][0]["text"] == "테스트 제목"
    assert comp["layout"] == "default"
    assert comp["align"] == "left"


def test_create_image_component():
    img_data = {
        "url": "https://example.com/img.png",
        "width": 800,
        "height": 600,
        "filename": "img.png",
    }
    comp = create_image_component(img_data)
    assert comp["@ctype"] == "image"
    assert comp["src"] == "https://example.com/img.png"
    assert comp["width"] == 800
    assert comp["height"] == 600
    assert comp["fileName"] == "img.png"


def test_create_image_component_defaults():
    img_data = {"url": "https://example.com/img.png"}
    comp = create_image_component(img_data)
    assert comp["width"] == 0
    assert comp["height"] == 0
    assert comp["fileName"] == ""
