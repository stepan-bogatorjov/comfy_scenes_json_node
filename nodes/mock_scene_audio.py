import torch


class MockSceneAudio:
    MODELS = ["eleven_multilingual_v2", "eleven_turbo_v2_5", "eleven_flash_v2_5", "mock"]
    NORMALIZATIONS = ["auto", "on", "off"]
    OUTPUT_FORMATS = [
        "mp3_44100_192",
        "mp3_44100_128",
        "mp3_22050_32",
        "pcm_44100",
        "pcm_22050",
    ]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"multiline": True, "default": ""}),
                "stability": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01}),
                "apply_text_normalization": (cls.NORMALIZATIONS, {"default": "auto"}),
                "model": (cls.MODELS, {"default": "eleven_multilingual_v2"}),
                "speed": ("FLOAT", {"default": 1.0, "min": 0.5, "max": 2.0, "step": 0.01}),
                "similarity_boost": ("FLOAT", {"default": 0.75, "min": 0.0, "max": 1.0, "step": 0.01}),
                "use_speaker_boost": ("BOOLEAN", {"default": False}),
                "style": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "language_code": ("STRING", {"default": ""}),
                "seed": ("INT", {"default": 1, "min": 0, "max": 0xFFFFFFFFFFFFFFFF}),
                "output_format": (cls.OUTPUT_FORMATS, {"default": "mp3_44100_192"}),
            },
            "optional": {
                "voice": ("ELEVENLABS_VOICE",),
            },
        }

    RETURN_TYPES = ("AUDIO",)
    RETURN_NAMES = ("AUDIO",)
    FUNCTION = "generate"
    CATEGORY = "mock"

    @staticmethod
    def _resolve_sample_rate(output_format):
        for token in output_format.split("_"):
            if token.isdigit() and len(token) >= 4:
                return int(token)
        return 44100

    def generate(self, text, stability, apply_text_normalization, model, speed,
                 similarity_boost, use_speaker_boost, style, language_code, seed,
                 output_format, voice=None):
        sample_rate = self._resolve_sample_rate(output_format)

        chars = max(1, len(text))
        base_seconds = chars / 15.0
        seconds = max(0.5, base_seconds / max(0.1, float(speed)))
        num_samples = int(seconds * sample_rate)

        generator = torch.Generator().manual_seed(int(seed) & 0xFFFFFFFF)

        t = torch.linspace(0.0, seconds, num_samples)
        freq = 180.0 + 120.0 * float(stability)
        tone = 0.15 * torch.sin(2.0 * torch.pi * freq * t)
        noise = (torch.rand(num_samples, generator=generator) - 0.5) * 0.02 * float(style)
        waveform = (tone + noise).unsqueeze(0).unsqueeze(0)

        print(
            f"[MockSceneAudio] seed={seed} model={model} sr={sample_rate} "
            f"duration={seconds:.2f}s speed={speed} stability={stability} "
            f"similarity_boost={similarity_boost} style={style} "
            f"speaker_boost={use_speaker_boost} norm={apply_text_normalization} "
            f"lang={language_code!r} fmt={output_format} voice={voice!r} "
            f"text[:60]={text[:60]!r}"
        )

        return ({"waveform": waveform, "sample_rate": sample_rate},)


NODE_CLASS_MAPPINGS = {
    "MockSceneAudio": MockSceneAudio,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MockSceneAudio": "Mock Scene Audio",
}
