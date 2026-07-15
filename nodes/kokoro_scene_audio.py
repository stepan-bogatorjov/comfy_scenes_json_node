"""Local (offline, free) text-to-speech scene audio using Kokoro-82M.

Drop-in replacement for the ElevenLabs-backed MockSceneAudio: same AUDIO
output shape ({"waveform": [1, 1, N], "sample_rate": int}) so it plugs into
the exact same spot in the story pipeline. Voices are selected by name, just
like the old flow, but generation happens entirely on the local GPU/CPU with
no API key and no per-character cost.
"""

import torch

# --- Kokoro voice catalogue (Kokoro-82M v1.0) -----------------------------
# Prefix meaning: a* = American English, b* = British English,
#                 *f_ = female, *m_ = male.
AMERICAN_FEMALE = [
    "af_heart", "af_alloy", "af_aoede", "af_bella", "af_jessica",
    "af_kore", "af_nicole", "af_nova", "af_river", "af_sarah", "af_sky",
]
AMERICAN_MALE = [
    "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam",
    "am_michael", "am_onyx", "am_puck", "am_santa",
]
BRITISH_FEMALE = ["bf_alice", "bf_emma", "bf_isabella", "bf_lily"]
BRITISH_MALE = ["bm_daniel", "bm_fable", "bm_george", "bm_lewis"]

KOKORO_VOICES = AMERICAN_FEMALE + AMERICAN_MALE + BRITISH_FEMALE + BRITISH_MALE

SAMPLE_RATE = 24000  # Kokoro always outputs 24 kHz mono.

# Lazily-built pipeline cache, keyed by language code ('a' American, 'b' British).
_PIPELINES = {}


def _get_pipeline(lang_code):
    """Return a cached KPipeline for the given language code, building it once."""
    pipe = _PIPELINES.get(lang_code)
    if pipe is None:
        from kokoro import KPipeline  # imported lazily so the pack still loads

        device = "cuda" if torch.cuda.is_available() else "cpu"
        try:
            pipe = KPipeline(lang_code=lang_code, device=device)
        except TypeError:
            # Older kokoro versions have no `device` kwarg; it auto-detects.
            pipe = KPipeline(lang_code=lang_code)
        _PIPELINES[lang_code] = pipe
    return pipe


class KokoroSceneAudio:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"multiline": True, "default": ""}),
                "voice": (KOKORO_VOICES, {"default": "am_michael"}),
                "speed": ("FLOAT", {"default": 1.0, "min": 0.5, "max": 2.0, "step": 0.05}),
                # Pitch shift in semitones (duration preserved). Kokoro has no
                # dedicated child voice; +4..+7 over a light voice (af_sky,
                # af_alloy, bf_lily) gives a convincing childlike timbre.
                # Negative values deepen the voice. 0 = untouched.
                "pitch": ("FLOAT", {"default": 0.0, "min": -12.0, "max": 12.0, "step": 0.5}),
            },
            "optional": {
                # When connected, a voice name coming from the story JSON
                # (e.g. "Roger", "Sarah", or a raw kokoro id) overrides the
                # dropdown above via StringToKokoroVoice-style resolution.
                "voice_name": ("STRING", {"forceInput": True}),
            },
        }

    RETURN_TYPES = ("AUDIO",)
    RETURN_NAMES = ("AUDIO",)
    FUNCTION = "generate"
    CATEGORY = "audio"

    @staticmethod
    def _resolve_voice(voice, voice_name):
        candidate = (voice_name or "").strip()
        if candidate:
            # Accept a raw kokoro id directly, otherwise map a friendly/legacy
            # name via the shared resolver (its pitch is ignored here - pitch
            # arrives through the node's own `pitch` input from the mapper).
            if candidate in KOKORO_VOICES:
                return candidate
            from .string_to_kokoro_voice import resolve
            resolved_voice, _pitch = resolve(candidate)
            return resolved_voice
        return voice

    @staticmethod
    def _apply_pitch(mono, semitones):
        """Shift pitch by `semitones` (duration preserved) via torchaudio."""
        if abs(semitones) < 1e-3:
            return mono
        import torchaudio

        shifter = torchaudio.transforms.PitchShift(SAMPLE_RATE, n_steps=float(semitones))
        with torch.no_grad():
            shifted = shifter(mono.unsqueeze(0)).squeeze(0).detach()
        peak = float(shifted.abs().max())
        if peak > 1.0:  # keep it from clipping after the shift
            shifted = shifted / peak * 0.98
        return shifted

    def generate(self, text, voice, speed, pitch=0.0, voice_name=None):
        resolved = self._resolve_voice(voice, voice_name)
        lang_code = resolved[0] if resolved and resolved[0] in ("a", "b") else "a"
        pipe = _get_pipeline(lang_code)

        clean_text = (text or "").strip()
        if not clean_text:
            # Empty narration -> a short silence so the pipeline never crashes.
            waveform = torch.zeros(1, 1, SAMPLE_RATE // 2)
            print("[KokoroSceneAudio] empty text -> 0.5s silence")
            return ({"waveform": waveform, "sample_rate": SAMPLE_RATE},)

        chunks = []
        for _graphemes, _phonemes, audio in pipe(clean_text, voice=resolved, speed=float(speed)):
            if audio is not None:
                chunks.append(audio.detach().to("cpu").float())

        if chunks:
            mono = self._apply_pitch(torch.cat(chunks), pitch)
            wav = mono.unsqueeze(0).unsqueeze(0)  # [1, 1, N]
        else:
            wav = torch.zeros(1, 1, SAMPLE_RATE // 2)

        duration = wav.shape[-1] / SAMPLE_RATE
        print(
            f"[KokoroSceneAudio] voice={resolved} speed={speed} pitch={pitch:+.1f}st "
            f"sr={SAMPLE_RATE} duration={duration:.2f}s text[:60]={clean_text[:60]!r}"
        )
        return ({"waveform": wav, "sample_rate": SAMPLE_RATE},)


NODE_CLASS_MAPPINGS = {
    "KokoroSceneAudio": KokoroSceneAudio,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "KokoroSceneAudio": "Kokoro Scene Audio (local TTS)",
}
