from .nodes.save_video_passthrough_node import SaveVideoPassthrough
from .nodes.save_image_passthrough_node import SaveImagePassthrough
from .nodes.save_audio_passthrough_node import SaveAudioPassthrough
from .nodes.save_text_passthrough_node import SaveTextPassthrough
from .nodes.mock_generators import MockSceneImage, MockSceneVideo
from .nodes.mock_scene_audio import MockSceneAudio
from .nodes.mock_scene_text import MockSceneText
from .nodes.string_to_elevenlabs_voice import StringToElevenLabsVoice
from .nodes.story_final_compile import StoryFinalCompile
from .nodes.youtube_trend_topics import YoutubeTrendTopics
from .nodes.collect_run_outputs import CollectRunOutputs

NODE_CLASS_MAPPINGS = {
    "SaveVideoPassthrough": SaveVideoPassthrough,
    "SaveImagePassthrough": SaveImagePassthrough,
    "SaveAudioPassthrough": SaveAudioPassthrough,
    "SaveTextPassthrough": SaveTextPassthrough,
    "MockSceneImage": MockSceneImage,
    "MockSceneVideo": MockSceneVideo,
    "MockSceneAudio": MockSceneAudio,
    "MockSceneText": MockSceneText,
    "StringToElevenLabsVoice": StringToElevenLabsVoice,
    "StoryFinalCompile": StoryFinalCompile,
    "YoutubeTrendTopics": YoutubeTrendTopics,
    "CollectRunOutputs": CollectRunOutputs,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SaveVideoPassthrough": "Save Video Passthrough",
    "SaveImagePassthrough": "Save Image Passthrough",
    "SaveAudioPassthrough": "Save Audio Passthrough",
    "SaveTextPassthrough": "Save Text Passthrough",
    "MockSceneImage": "Mock Scene Image",
    "MockSceneVideo": "Mock Scene Video",
    "MockSceneAudio": "Mock Scene Audio",
    "MockSceneText": "Mock Scene Text",
    "StringToElevenLabsVoice": "String -> ElevenLabs Voice",
    "StoryFinalCompile": "Story Final Compile",
    "YoutubeTrendTopics": "YouTube Trend Topics",
    "CollectRunOutputs": "Collect Run Outputs",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
