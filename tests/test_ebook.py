"""Tests for EPUB ebook parsing module."""

import pytest
from ebooklib import epub

from transcriber.ebook import _html_to_text, _walk_toc, match_chapter
from transcriber.models import TocEntry

# --- _html_to_text tests ---


def test_html_to_text_paragraphs():
    html = "<p>First paragraph.</p><p>Second paragraph.</p>"
    result = _html_to_text(html)
    assert "First paragraph." in result
    assert "Second paragraph." in result
    assert "\n\n" in result


def test_html_to_text_strips_tags():
    html = "<p>This is <b>bold</b> and <i>italic</i> text.</p>"
    result = _html_to_text(html)
    assert "<b>" not in result
    assert "<i>" not in result
    assert "bold" in result
    assert "italic" in result


def test_html_to_text_removes_script_style():
    html = "<p>Content</p><script>alert('xss')</script><style>.x{color:red}</style><p>More</p>"
    result = _html_to_text(html)
    assert "alert" not in result
    assert "color" not in result
    assert "Content" in result
    assert "More" in result


def test_html_to_text_headings():
    html = "<h1>Title</h1><p>Body text here.</p>"
    result = _html_to_text(html)
    assert "Title" in result
    assert "Body text here." in result


def test_html_to_text_empty():
    assert _html_to_text("") == ""
    assert _html_to_text(None) == ""


def test_html_to_text_nested_divs():
    html = "<div><div><p>Nested content.</p></div></div>"
    result = _html_to_text(html)
    assert "Nested content." in result


def test_html_to_text_list_items():
    html = "<ul><li>Item one</li><li>Item two</li></ul>"
    result = _html_to_text(html)
    assert "Item one" in result
    assert "Item two" in result


# --- match_chapter tests ---


@pytest.fixture
def sample_toc():
    return [
        TocEntry(index=0, title="Introduction", level=0, href="intro.xhtml", number="1"),
        TocEntry(index=1, title="Getting Started", level=0, href="ch1.xhtml", number="2"),
        TocEntry(index=2, title="Basic Concepts", level=1, href="ch1_1.xhtml", number="2.1"),
        TocEntry(index=3, title="Advanced Topics", level=1, href="ch1_2.xhtml", number="2.2"),
        TocEntry(index=4, title="Conclusion", level=0, href="conclusion.xhtml", number="3"),
    ]


def test_match_by_hierarchical_number(sample_toc):
    result = match_chapter(sample_toc, "2.1")
    assert result.title == "Basic Concepts"
    assert result.index == 2


def test_match_by_index(sample_toc):
    result = match_chapter(sample_toc, "0")
    assert result.title == "Introduction"


def test_match_by_title_substring(sample_toc):
    result = match_chapter(sample_toc, "Advanced")
    assert result.title == "Advanced Topics"
    assert result.number == "2.2"


def test_match_by_title_case_insensitive(sample_toc):
    result = match_chapter(sample_toc, "getting started")
    assert result.title == "Getting Started"


def test_match_no_result(sample_toc):
    with pytest.raises(ValueError, match="No chapter matching"):
        match_chapter(sample_toc, "Nonexistent Chapter")


def test_match_hierarchical_number_priority(sample_toc):
    """Hierarchical number should match before index."""
    result = match_chapter(sample_toc, "3")
    assert result.title == "Conclusion"
    assert result.number == "3"


# --- _walk_toc tests ---


def test_walk_toc_flat_links():
    """Test walking a flat list of epub.Link items."""
    links = [
        epub.Link("ch1.xhtml", "Chapter 1", "ch1"),
        epub.Link("ch2.xhtml", "Chapter 2", "ch2"),
    ]
    entries = _walk_toc(links)
    assert len(entries) == 2
    assert entries[0].title == "Chapter 1"
    assert entries[0].number == "1"
    assert entries[0].level == 0
    assert entries[1].title == "Chapter 2"
    assert entries[1].number == "2"
    assert entries[1].index == 1


def test_walk_toc_nested():
    """Test walking nested TOC with Section + children."""
    section = epub.Section("Part One")
    children = [
        epub.Link("ch1.xhtml", "Chapter 1", "ch1"),
        epub.Link("ch2.xhtml", "Chapter 2", "ch2"),
    ]
    toc = [(section, children)]
    entries = _walk_toc(toc)
    assert len(entries) == 3
    assert entries[0].title == "Part One"
    assert entries[0].level == 0
    assert entries[0].number == "1"
    assert entries[1].title == "Chapter 1"
    assert entries[1].level == 1
    assert entries[1].number == "1.1"
    assert entries[2].title == "Chapter 2"
    assert entries[2].level == 1
    assert entries[2].number == "1.2"


def test_walk_toc_strips_fragment():
    """Test that href fragments are stripped."""
    links = [epub.Link("chapter.xhtml#section1", "Section", "sec1")]
    entries = _walk_toc(links)
    assert entries[0].href == "chapter.xhtml"


def test_walk_toc_mixed():
    """Test mix of Links and Sections."""
    toc = [
        epub.Link("preface.xhtml", "Preface", "preface"),
        (
            epub.Section("Part 1"),
            [epub.Link("ch1.xhtml", "Chapter 1", "ch1")],
        ),
    ]
    entries = _walk_toc(toc)
    assert len(entries) == 3
    assert entries[0].title == "Preface"
    assert entries[0].number == "1"
    assert entries[1].title == "Part 1"
    assert entries[1].number == "2"
    assert entries[2].title == "Chapter 1"
    assert entries[2].number == "2.1"
