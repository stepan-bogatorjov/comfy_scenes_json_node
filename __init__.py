from .nodes.save_video_passthrough_node import SaveVideoPassthrough
from .nodes.save_image_passthrough_node import SaveImagePassthrough
from .nodes.save_audio_passthrough_node import SaveAudioPassthrough
from .nodes.mock_generators import MockSceneImage, MockSceneVideo
from .nodes.mock_scene_audio import MockSceneAudio
from .nodes.string_to_elevenlabs_voice import StringToElevenLabsVoice
from .nodes.story_final_compile import StoryFinalCompile

NODE_CLASS_MAPPINGS = {
    "SaveVideoPassthrough": SaveVideoPassthrough,
    "SaveImagePassthrough": SaveImagePassthrough,
    "SaveAudioPassthrough": SaveAudioPassthrough,
    "MockSceneImage": MockSceneImage,
    "MockSceneVideo": MockSceneVideo,
    "MockSceneAudio": MockSceneAudio,
    "StringToElevenLabsVoice": StringToElevenLabsVoice,
    "StoryFinalCompile": StoryFinalCompile,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SaveVideoPassthrough": "Save Video Passthrough",
    "SaveImagePassthrough": "Save Image Passthrough",
    "SaveAudioPassthrough": "Save Audio Passthrough",
    "MockSceneImage": "Mock Scene Image",
    "MockSceneVideo": "Mock Scene Video",
    "MockSceneAudio": "Mock Scene Audio",
    "StringToElevenLabsVoice": "String -> ElevenLabs Voice",
    "StoryFinalCompile": "Story Final Compile",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
