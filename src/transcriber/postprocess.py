"""Post-processing module for filler removal and speaker naming."""

import re

# Filler words to remove (case-insensitive)
FILLER_WORDS = {
    # Hesitation sounds
    "um",
    "uh",
    "er",
    "ah",
    "hmm",
    "mm",
    "mhm",
    "erm",
    # Common fillers
    "like",  # Will be handled with context
    "basically",
    "literally",
    "actually",
    "honestly",
    "obviously",
    "definitely",
}

# Multi-word fillers
FILLER_PHRASES = [
    "you know",
    "i mean",
    "sort of",
    "kind of",
    "you know what i mean",
    "if you will",
    "as it were",
    "so to speak",
]

# Patterns for speaker name identification (strict to avoid false positives)
# Names must be capitalized proper nouns (not common words)
COMMON_WORDS = {
    "all", "going", "the", "this", "that", "just", "well", "here", "there",
    "what", "when", "where", "which", "how", "why", "now", "then", "very",
    "really", "actually", "basically", "literally", "honestly", "obviously",
    "definitely", "probably", "maybe", "certainly", "clearly", "simply",
    "okay", "yeah", "yes", "right", "sure", "great", "good", "nice", "fine",
}

NAME_PATTERNS = [
    # "My name is [Name]" - most reliable
    r"my name is\s+([A-Z][a-z]{2,})",
    # "I'm [Name]" at sentence start - must be followed by comma/period or "and"
    r"^I'm\s+([A-Z][a-z]{2,})(?:\s*[,.]|\s+and\b)",
    # "[Name] here" at sentence start
    r"^([A-Z][a-z]{2,})\s+here\b",
    # "This is [Name]" for introductions
    r"this is\s+([A-Z][a-z]{2,})",
]


def remove_fillers_from_text(text: str) -> str:
    """
    Remove filler words and phrases from text.

    Args:
        text: Input text

    Returns:
        Cleaned text with fillers removed
    """
    result = text

    # Remove multi-word fillers first (order matters)
    for phrase in FILLER_PHRASES:
        # Match phrase with optional surrounding punctuation/whitespace
        pattern = rf"\b{re.escape(phrase)}\b[,.]?\s*"
        result = re.sub(pattern, " ", result, flags=re.IGNORECASE)

    # Remove single-word fillers
    for filler in FILLER_WORDS:
        # Match standalone filler words (not part of larger words)
        # Be careful with "like" - only remove when standalone
        if filler == "like":
            # Remove "like" when it's a filler (comma or start of clause)
            pattern = r"(?:^|,\s*)\blike\b[,]?\s*"
        else:
            pattern = rf"\b{re.escape(filler)}\b[,.]?\s*"
        result = re.sub(pattern, " ", result, flags=re.IGNORECASE)

    # Clean up multiple spaces and trim
    result = re.sub(r"\s+", " ", result).strip()

    # Fix sentence capitalization after removing fillers
    result = re.sub(r"(?<=\.\s)([a-z])", lambda m: m.group(1).upper(), result)

    return result


def remove_fillers_from_segments(segments: list[dict]) -> list[dict]:
    """
    Remove fillers from each segment's text.

    Args:
        segments: List of segment dicts with 'text' field

    Returns:
        Segments with cleaned text
    """
    return [
        {**seg, "text": remove_fillers_from_text(seg["text"])}
        for seg in segments
        if remove_fillers_from_text(seg["text"]).strip()  # Remove empty segments
    ]


def identify_speaker_names(segments: list[dict]) -> dict[str, str]:
    """
    Attempt to identify speaker names from transcript content.

    Looks for patterns like "I'm [Name]", "My name is [Name]", etc.

    Args:
        segments: List of segments with 'speaker' and 'text' fields

    Returns:
        Dict mapping speaker labels to identified names
    """
    speaker_names: dict[str, str] = {}

    for segment in segments:
        speaker = segment.get("speaker", "")
        text = segment.get("text", "")

        if speaker in speaker_names:
            continue  # Already identified

        for pattern in NAME_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                name = match.group(1)
                # Validate it looks like a name:
                # - Reasonable length (3-20 chars)
                # - Not a common word
                # - Starts with capital letter
                if (
                    name
                    and 3 <= len(name) <= 20
                    and name.lower() not in COMMON_WORDS
                    and name[0].isupper()
                ):
                    speaker_names[speaker] = name.capitalize()
                    break

    return speaker_names


def apply_speaker_names(segments: list[dict], speaker_names: dict[str, str]) -> list[dict]:
    """
    Replace generic speaker labels with identified names.

    Args:
        segments: List of segments
        speaker_names: Mapping of speaker labels to names

    Returns:
        Segments with updated speaker names
    """
    return [
        {**seg, "speaker": speaker_names.get(seg["speaker"], seg["speaker"])}
        for seg in segments
    ]


def process_transcript(
    segments: list[dict],
    remove_fillers: bool = True,
    identify_speakers: bool = True,
) -> tuple[list[dict], dict[str, str]]:
    """
    Full post-processing pipeline.

    Args:
        segments: Raw transcript segments
        remove_fillers: Whether to remove filler words
        identify_speakers: Whether to attempt speaker identification

    Returns:
        Tuple of (processed segments, speaker name mapping)
    """
    result = segments

    # Identify speakers first (before removing fillers that might contain names)
    speaker_names = {}
    if identify_speakers:
        speaker_names = identify_speaker_names(result)
        result = apply_speaker_names(result, speaker_names)

    # Remove fillers
    if remove_fillers:
        result = remove_fillers_from_segments(result)

    return result, speaker_names
