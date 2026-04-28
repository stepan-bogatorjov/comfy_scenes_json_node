from .nodes.save_video_passthrough_node import SaveVideoPassthrough
from .nodes.save_image_passthrough_node import SaveImagePassthrough
from .nodes.mock_generators import MockSceneImage, MockSceneVideo

NODE_CLASS_MAPPINGS = {
    "SaveVideoPassthrough": SaveVideoPassthrough,
    "SaveImagePassthrough": SaveImagePassthrough,
    "MockSceneImage": MockSceneImage,
    "MockSceneVideo": MockSceneVideo,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SaveVideoPassthrough": "Save Video Passthrough",
    "SaveImagePassthrough": "Save Image Passthrough",
    "MockSceneImage": "Mock Scene Image",
    "MockSceneVideo": "Mock Scene Video",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
