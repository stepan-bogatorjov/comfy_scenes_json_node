"""StoryJsonLoader — ComfyUI node that parses a story JSON and returns global story data."""

from ..utils.json_parser import load_story_json


class StoryJsonLoader:
    """Load a story JSON and output global metadata + reference image prompt."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": {
                "json_text": ("STRING", {"multiline": True, "default": ""}),
                "file_path": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("title", "viral_title", "description", "reference_image_prompt")
    FUNCTION = "load_story"
    CATEGORY = "ViralStory"

    def load_story(self, json_text="", file_path=""):
        data = load_story_json(json_text, file_path)

        return (
            str(data["title"]),
            str(data["viralTitle"]),
            str(data["description"]),
            str(data["reference_image_prompt"]),
        )
