from .nodes.save_video_passthrough_node import SaveVideoPassthrough
from .nodes.save_image_passthrough_node import SaveImagePassthrough
from .nodes.save_audio_passthrough_node import SaveAudioPassthrough
from .nodes.save_text_passthrough_node import SaveTextPassthrough
from .nodes.mock_generators import MockSceneImage, MockSceneVideo
from .nodes.mock_scene_audio import MockSceneAudio
from .nodes.mock_scene_text import MockSceneText
from .nodes.string_to_elevenlabs_voice import StringToElevenLabsVoice
from .nodes.kokoro_scene_audio import KokoroSceneAudio
from .nodes.string_to_kokoro_voice import StringToKokoroVoice
from .nodes.story_final_compile import StoryFinalCompile
from .nodes.youtube_trend_topics import YoutubeTrendTopics
from .nodes.collect_run_outputs import CollectRunOutputs
from .nodes.load_images_by_names import LoadImagesByNames
from .nodes.video_last_frame import VideoLastFrame
from .nodes.musicgen_audio import MusicGenAudio

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
    "KokoroSceneAudio": KokoroSceneAudio,
    "StringToKokoroVoice": StringToKokoroVoice,
    "StoryFinalCompile": StoryFinalCompile,
    "YoutubeTrendTopics": YoutubeTrendTopics,
    "CollectRunOutputs": CollectRunOutputs,
    "LoadImagesByNames": LoadImagesByNames,
    "VideoLastFrame": VideoLastFrame,
    "MusicGenAudio": MusicGenAudio,
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
    "KokoroSceneAudio": "Kokoro Scene Audio (local TTS)",
    "StringToKokoroVoice": "String -> Kokoro Voice",
    "StoryFinalCompile": "Story Final Compile",
    "YoutubeTrendTopics": "YouTube Trend Topics",
    "CollectRunOutputs": "Collect Run Outputs",
    "LoadImagesByNames": "Load Images By Names",
    "VideoLastFrame": "Video Last Frame",
    "MusicGenAudio": "MusicGen Audio (local music)",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
