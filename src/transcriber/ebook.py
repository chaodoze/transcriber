"""EPUB ebook parsing for chapter-by-chapter reading."""

import re
from pathlib import Path

from bs4 import BeautifulSoup, Tag
from ebooklib import ITEM_DOCUMENT, epub

from .models import EbookChapterResult, EbookTocResult, TocEntry


def parse_epub(file_path: str) -> epub.EpubBook:
    """Open and validate an EPUB file."""
    path = Path(file_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if path.suffix.lower() != ".epub":
        raise ValueError(f"Not an EPUB file: {path}")
    return epub.read_epub(str(path))


def get_book_metadata(book: epub.EpubBook) -> dict:
    """Extract title, authors, language from Dublin Core metadata."""
    title = book.get_metadata("DC", "title")
    title = title[0][0] if title else "Unknown"

    authors = book.get_metadata("DC", "creator")
    authors = [a[0] for a in authors] if authors else []

    language = book.get_metadata("DC", "language")
    language = language[0][0] if language else None

    return {"title": title, "authors": authors, "language": language}


def _walk_toc(toc_items, level: int = 0, counters: list | None = None) -> list[TocEntry]:
    """Recursively walk EPUB TOC structure into a flat list with hierarchical numbering.

    EPUB toc items are either:
    - epub.Link (leaf node with title, href)
    - tuple of (epub.Section, list_of_children) for nested sections
    """
    if counters is None:
        counters = []

    entries = []
    position = 0

    for item in toc_items:
        position += 1

        # Build hierarchical number
        current_counters = counters + [position]
        number = ".".join(str(c) for c in current_counters)

        if isinstance(item, epub.Link):
            # Strip fragment from href (e.g., "chapter1.xhtml#sec1" -> "chapter1.xhtml")
            href = item.href.split("#")[0] if item.href else ""
            entries.append(
                TocEntry(
                    index=len(entries),
                    title=item.title or "",
                    level=level,
                    href=href,
                    number=number,
                )
            )
        elif isinstance(item, tuple) and len(item) == 2:
            section, children = item
            title = section.title if hasattr(section, "title") else str(section)
            # Section itself is a TOC entry
            href = ""
            if hasattr(section, "href") and section.href:
                href = section.href.split("#")[0]
            entries.append(
                TocEntry(
                    index=len(entries),
                    title=title,
                    level=level,
                    href=href,
                    number=number,
                )
            )
            # Recurse into children, updating indices
            child_entries = _walk_toc(children, level=level + 1, counters=current_counters)
            for child in child_entries:
                child.index = len(entries)
                entries.append(child)

    return entries


def _build_toc_from_spine(book: epub.EpubBook) -> list[TocEntry]:
    """Fallback: build TOC from spine order using heading tags."""
    entries = []
    for item in book.get_items_of_type(ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), "lxml")
        heading = soup.find(re.compile(r"^h[1-3]$"))
        title = heading.get_text(strip=True) if heading else item.get_name()
        entries.append(
            TocEntry(
                index=len(entries),
                title=title,
                level=0,
                href=item.get_name(),
                number=str(len(entries) + 1),
            )
        )
    return entries


def extract_toc(book: epub.EpubBook) -> list[TocEntry]:
    """Extract table of contents from EPUB, with spine fallback."""
    toc = book.toc
    if toc:
        entries = _walk_toc(toc)
        if entries:
            return entries
    return _build_toc_from_spine(book)


def _html_to_text(html: str | bytes) -> str:
    """Convert HTML to plain text with paragraph breaks."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")

    # Remove script and style elements
    for tag in soup.find_all(["script", "style"]):
        tag.decompose()

    # Block-level elements that should have paragraph breaks
    block_tags = {
        "p",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "blockquote",
        "li",
        "tr",
        "br",
        "hr",
    }

    parts: list[str] = []
    for element in soup.descendants:
        if isinstance(element, str):
            text = element.strip()
            if text:
                parts.append(text)
        elif isinstance(element, Tag) and element.name in block_tags:
            parts.append("\n\n")

    # Join, collapse whitespace, and clean up
    text = " ".join(parts)
    # Normalize paragraph breaks
    text = re.sub(r"\s*\n\n\s*", "\n\n", text)
    # Collapse multiple spaces within paragraphs
    text = re.sub(r"[^\S\n]+", " ", text)
    # Remove leading/trailing whitespace per paragraph
    paragraphs = [p.strip() for p in text.split("\n\n")]
    paragraphs = [p for p in paragraphs if p]
    return "\n\n".join(paragraphs)


def extract_chapter_text(book: epub.EpubBook, href: str) -> str:
    """Get plain text content for a chapter by its href."""
    item = book.get_item_with_href(href)
    if item is None:
        raise ValueError(f"Chapter not found: {href}")
    return _html_to_text(item.get_content())


def match_chapter(toc: list[TocEntry], query: str) -> TocEntry:
    """Match a chapter query against TOC entries.

    Priority:
    1. Hierarchical number (e.g., "3.1")
    2. Index (plain integer)
    3. Title substring (case-insensitive)
    """
    query = query.strip()

    # 1. Try hierarchical number match
    for entry in toc:
        if entry.number and entry.number == query:
            return entry

    # 2. Try index match (plain integer)
    if query.isdigit():
        idx = int(query)
        for entry in toc:
            if entry.index == idx:
                return entry

    # 3. Try title substring match (case-insensitive)
    query_lower = query.lower()
    for entry in toc:
        if query_lower in entry.title.lower():
            return entry

    raise ValueError(f"No chapter matching '{query}'. Use ebook_toc to see available chapters.")


def get_toc(file_path: str) -> EbookTocResult:
    """Get the table of contents for an EPUB file."""
    book = parse_epub(file_path)
    metadata = get_book_metadata(book)
    toc = extract_toc(book)

    return EbookTocResult(
        title=metadata["title"],
        authors=metadata["authors"],
        language=metadata["language"],
        toc=toc,
        total_chapters=len(toc),
    )


def get_chapter(file_path: str, chapter_query: str) -> EbookChapterResult:
    """Get the content of a specific chapter from an EPUB file."""
    book = parse_epub(file_path)
    metadata = get_book_metadata(book)
    toc = extract_toc(book)

    entry = match_chapter(toc, chapter_query)
    content = extract_chapter_text(book, entry.href)

    # Navigation context
    prev_chapter = None
    next_chapter = None
    if entry.index > 0:
        prev_entry = toc[entry.index - 1]
        prev_chapter = (
            f"{prev_entry.number}: {prev_entry.title}" if prev_entry.number else prev_entry.title
        )
    if entry.index < len(toc) - 1:
        next_entry = toc[entry.index + 1]
        next_chapter = (
            f"{next_entry.number}: {next_entry.title}" if next_entry.number else next_entry.title
        )

    return EbookChapterResult(
        book_title=metadata["title"],
        chapter_title=entry.title,
        chapter_number=entry.number,
        chapter_index=entry.index,
        content=content,
        word_count=len(content.split()),
        prev_chapter=prev_chapter,
        next_chapter=next_chapter,
    )
