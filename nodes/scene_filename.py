"""StorySceneFilename — ComfyUI node that generates a safe filename for save nodes."""

import re
import unicodedata


class StorySceneFilename:
    """Generate a filesystem-safe filename from the story title and scene number."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "title": ("STRING", {"default": ""}),
                "scene_number": ("INT", {"default": 1, "min": 1, "step": 1}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("safe_filename",)
    FUNCTION = "generate_filename"
    CATEGORY = "ViralStory"

    def generate_filename(self, title: str, scene_number: int):
        safe = _sanitize_title(title)
        filename = f"{safe}_scene_{scene_number:02d}"
        return (filename,)


def _sanitize_title(title: str) -> str:
    """Convert a title string into a lowercase, underscore-separated safe filename stem.

    Example: "The Quicksand Sink" -> "the_quicksand_sink"
    """
    # Normalize unicode characters to ASCII equivalents where possible
    normalized = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    lowered = normalized.lower().strip()
    # Replace any non-alphanumeric character (except underscore) with underscore
    cleaned = re.sub(r"[^a-z0-9]+", "_", lowered)
    # Strip leading/trailing underscores
    return cleaned.strip("_")
