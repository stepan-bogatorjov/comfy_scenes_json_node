"""Shared utility for loading and validating story JSON data."""

import json
import os

# Required top-level keys in the story JSON
_REQUIRED_STORY_KEYS = {"title", "viralTitle", "description", "reference_image_prompt", "scenes"}

# Required keys in each scene object
_REQUIRED_SCENE_KEYS = {"scene", "duration", "image_prompt", "video_prompt"}


def load_story_json(json_text: str = "", file_path: str = "") -> dict:
    """Load and validate a story JSON from either raw text or a file path.

    Args:
        json_text: Raw JSON string. Preferred if non-empty.
        file_path: Path to a .json file. Used as fallback when json_text is empty.

    Returns:
        Parsed and validated story dictionary.

    Raises:
        ValueError: If inputs are missing, JSON is malformed, or structure is invalid.
    """
    raw = _resolve_raw_json(json_text, file_path)
    data = _parse_json(raw)
    _validate_story_structure(data)
    return data


def _resolve_raw_json(json_text: str, file_path: str) -> str:
    """Determine the raw JSON string from the provided inputs."""
    text = json_text.strip() if json_text else ""
    if text:
        return text

    path = file_path.strip() if file_path else ""
    if not path:
        raise ValueError(
            "StoryJSON: No input provided. "
            "Supply either json_text or a file_path."
        )

    if not os.path.isfile(path):
        raise ValueError(f"StoryJSON: File not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _parse_json(raw: str) -> dict:
    """Parse a raw JSON string into a dictionary."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"StoryJSON: Invalid JSON — {e}") from e

    if not isinstance(data, dict):
        raise ValueError("StoryJSON: Top-level JSON must be an object, got " + type(data).__name__)

    return data


def _validate_story_structure(data: dict) -> None:
    """Validate that the story dict has all required fields and correct types."""
    missing = _REQUIRED_STORY_KEYS - data.keys()
    if missing:
        raise ValueError(f"StoryJSON: Missing required keys: {sorted(missing)}")

    if not isinstance(data["scenes"], list):
        raise ValueError("StoryJSON: 'scenes' must be an array")

    if len(data["scenes"]) == 0:
        raise ValueError("StoryJSON: 'scenes' array is empty")

    for i, scene in enumerate(data["scenes"]):
        if not isinstance(scene, dict):
            raise ValueError(f"StoryJSON: scenes[{i}] must be an object")
        scene_missing = _REQUIRED_SCENE_KEYS - scene.keys()
        if scene_missing:
            raise ValueError(f"StoryJSON: scenes[{i}] missing keys: {sorted(scene_missing)}")
