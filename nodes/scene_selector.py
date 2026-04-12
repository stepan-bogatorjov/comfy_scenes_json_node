"""StorySceneSelector — ComfyUI node that extracts data for a single scene by index."""

from ..utils.json_parser import load_story_json


class StorySceneSelector:
    """Select a scene by zero-based index and output its prompt/duration data."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "scene_index": ("INT", {"default": 0, "min": 0, "step": 1}),
            },
            "optional": {
                "json_text": ("STRING", {"multiline": True, "default": ""}),
                "file_path": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("INT", "INT", "STRING", "STRING")
    RETURN_NAMES = ("scene_number", "duration", "image_prompt", "video_prompt")
    FUNCTION = "select_scene"
    CATEGORY = "ViralStory"

    def select_scene(self, scene_index=0, json_text="", file_path=""):
        data = load_story_json(json_text, file_path)
        scenes = data["scenes"]

        if scene_index < 0 or scene_index >= len(scenes):
            raise ValueError(
                f"StorySceneSelector: scene_index {scene_index} out of range. "
                f"Story has {len(scenes)} scenes (valid: 0–{len(scenes) - 1})."
            )

        scene = scenes[scene_index]

        return (
            int(scene["scene"]),
            int(scene["duration"]),
            str(scene["image_prompt"]),
            str(scene["video_prompt"]),
        )
