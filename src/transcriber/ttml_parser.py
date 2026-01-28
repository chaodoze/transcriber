"""Parse Apple Podcasts TTML transcripts to TranscriptResult format."""

import re
from pathlib import Path
from xml.etree import ElementTree as ET

from .models import Segment, TranscriptResult, TranscriptSource

# TTML XML namespaces
NAMESPACES = {
    "tt": "http://www.w3.org/ns/ttml",
    "ttm": "http://www.w3.org/ns/ttml#metadata",
    "podcasts": "http://podcasts.apple.com/transcript-ttml-internal",
}

# Register namespaces for cleaner output if needed
for prefix, uri in NAMESPACES.items():
    ET.register_namespace(prefix, uri)


def parse_ttml_timestamp(ts: str) -> float:
    """
    Parse TTML timestamp to seconds.

    Handles formats:
    - "0.860" (seconds only)
    - "1:48.737" (minutes:seconds)
    - "1:02:03.456" (hours:minutes:seconds)
    """
    if not ts:
        return 0.0

    parts = ts.split(":")
    if len(parts) == 1:
        # Just seconds
        return float(parts[0])
    elif len(parts) == 2:
        # minutes:seconds
        return float(parts[0]) * 60 + float(parts[1])
    elif len(parts) == 3:
        # hours:minutes:seconds
        return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])

    return 0.0


def extract_text_from_element(elem: ET.Element) -> str:
    """
    Extract text content from TTML element, including nested spans.

    Handles word-level spans and concatenates them with spaces.
    """
    # Check for word-level spans
    word_spans = elem.findall(".//tt:span[@podcasts:unit='word']", NAMESPACES)

    if word_spans:
        words = []
        for span in word_spans:
            if span.text:
                words.append(span.text.strip())
        return " ".join(words)

    # Fallback: get all text content
    text_parts = []
    if elem.text:
        text_parts.append(elem.text.strip())

    for child in elem:
        if child.text:
            text_parts.append(child.text.strip())
        if child.tail:
            text_parts.append(child.tail.strip())

    return " ".join(filter(None, text_parts))


def clean_speaker_label(speaker: str) -> str:
    """
    Clean speaker label from TTML format.

    Converts "SPEAKER_1" to "Speaker 1" etc.
    """
    if not speaker:
        return "Unknown"

    # Handle "SPEAKER_N" format
    match = re.match(r"SPEAKER[_\s]?(\d+)", speaker, re.IGNORECASE)
    if match:
        return f"Speaker {match.group(1)}"

    return speaker


def parse_ttml_file(ttml_path: Path, language: str = "en") -> TranscriptResult:
    """
    Parse TTML file into TranscriptResult format.

    Args:
        ttml_path: Path to TTML file
        language: Language code (default: "en")

    Returns:
        TranscriptResult with segments, speakers, and metadata
    """
    tree = ET.parse(ttml_path)
    root = tree.getroot()

    segments: list[Segment] = []
    speakers_seen: dict[str, str] = {}  # Map raw labels to clean labels

    # Find body element
    body = root.find(".//tt:body", NAMESPACES)
    if body is None:
        body = root.find("body")

    if body is None:
        raise ValueError(f"No body element found in TTML: {ttml_path}")

    # Get duration from body if available
    duration_attr = body.get("dur") or body.get("{http://www.w3.org/ns/ttml}dur")
    duration = float(duration_attr) if duration_attr else 0.0

    # Find all paragraph elements (typically contain speaker segments)
    paragraphs = root.findall(".//tt:p", NAMESPACES)
    if not paragraphs:
        paragraphs = root.findall(".//p")

    for p in paragraphs:
        # Get speaker from ttm:agent attribute
        speaker_raw = (
            p.get("{http://www.w3.org/ns/ttml#metadata}agent")
            or p.get("ttm:agent")
            or "Unknown"
        )
        speaker = clean_speaker_label(speaker_raw)

        # Track speakers
        if speaker_raw not in speakers_seen:
            speakers_seen[speaker_raw] = speaker

        # Get timestamps
        begin = p.get("begin") or "0"
        end = p.get("end") or "0"
        start_time = parse_ttml_timestamp(begin)
        end_time = parse_ttml_timestamp(end)

        # Extract text
        text = extract_text_from_element(p)

        if text.strip():
            segments.append(
                Segment(
                    speaker=speaker,
                    text=text.strip(),
                    start=start_time,
                    end=end_time,
                )
            )

    # Update duration from last segment if not set
    if not duration and segments:
        duration = segments[-1].end

    # Get unique speakers in order of appearance
    speakers = list(dict.fromkeys(seg.speaker for seg in segments))

    return TranscriptResult(
        segments=segments,
        speakers=speakers,
        duration=duration,
        language=language,
        source=TranscriptSource.APPLE_CACHE,
    )


def parse_ttml_string(ttml_content: str, language: str = "en") -> TranscriptResult:
    """
    Parse TTML content from string.

    Args:
        ttml_content: TTML XML content as string
        language: Language code (default: "en")

    Returns:
        TranscriptResult with segments, speakers, and metadata
    """
    root = ET.fromstring(ttml_content)

    # Reuse parsing logic by creating a temporary in-memory parse
    segments: list[Segment] = []
    speakers_seen: dict[str, str] = {}

    body = root.find(".//tt:body", NAMESPACES)
    if body is None:
        body = root.find("body")

    if body is None:
        raise ValueError("No body element found in TTML content")

    duration_attr = body.get("dur") or body.get("{http://www.w3.org/ns/ttml}dur")
    duration = float(duration_attr) if duration_attr else 0.0

    paragraphs = root.findall(".//tt:p", NAMESPACES)
    if not paragraphs:
        paragraphs = root.findall(".//p")

    for p in paragraphs:
        speaker_raw = (
            p.get("{http://www.w3.org/ns/ttml#metadata}agent")
            or p.get("ttm:agent")
            or "Unknown"
        )
        speaker = clean_speaker_label(speaker_raw)

        if speaker_raw not in speakers_seen:
            speakers_seen[speaker_raw] = speaker

        begin = p.get("begin") or "0"
        end = p.get("end") or "0"
        start_time = parse_ttml_timestamp(begin)
        end_time = parse_ttml_timestamp(end)

        text = extract_text_from_element(p)

        if text.strip():
            segments.append(
                Segment(
                    speaker=speaker,
                    text=text.strip(),
                    start=start_time,
                    end=end_time,
                )
            )

    if not duration and segments:
        duration = segments[-1].end

    speakers = list(dict.fromkeys(seg.speaker for seg in segments))

    return TranscriptResult(
        segments=segments,
        speakers=speakers,
        duration=duration,
        language=language,
        source=TranscriptSource.APPLE_CACHE,
    )
