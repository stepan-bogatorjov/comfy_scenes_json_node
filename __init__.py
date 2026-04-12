"""ComfyUI custom nodes for driving a scene workflow from a story JSON file."""

from .nodes.story_loader import StoryJsonLoader
from .nodes.scene_selector import StorySceneSelector
from .nodes.scene_filename import StorySceneFilename

NODE_CLASS_MAPPINGS = {
    "StoryJsonLoader": StoryJsonLoader,
    "StorySceneSelector": StorySceneSelector,
    "StorySceneFilename": StorySceneFilename,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "StoryJsonLoader": "Story JSON Loader",
    "StorySceneSelector": "Story Scene Selector",
    "StorySceneFilename": "Story Scene Filename",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
