"""Fast mock scene audio that mirrors the KokoroSceneAudio interface.

Same inputs (text / voice / speed / pitch / optional voice_name) and same
AUDIO output ({"waveform": [1, 1, N], "sample_rate": 24000}) as
KokoroSceneAudio, so the two nodes are drop-in interchangeable in the graph
with no rewiring. Instead of running the TTS model this just emits a short
pleasant tone whose length approximates the spoken text and whose pitch
tracks the chosen voice (male / female / child) and the `pitch` control -
instant, so iterating on the rest of the pipeline is fast and free.
"""

import os
import random

import torch

from .kokoro_scene_audio import KOKORO_VOICES, SAMPLE_RATE


def _base_freq(voice):
    """A base tone frequency (Hz) picked to reflect the voice's character."""
    # gender/register from the id prefix: *f_ female, *m_ male.
    is_female = len(voice) > 1 and voice[1] == "f"
    lo, hi = (250.0, 360.0) if is_female else (150.0, 240.0)
    # Deterministic per-voice within the band so each voice sounds distinct,
    # but seeded only by the name (not the clock) so a voice is recognizable.
    h = sum(ord(c) for c in voice)
    return lo + (h % 100) / 100.0 * (hi - lo)


class MockSceneAudio:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"multiline": True, "default": ""}),
                "voice": (KOKORO_VOICES, {"default": "am_michael"}),
                "speed": ("FLOAT", {"default": 1.0, "min": 0.5, "max": 2.0, "step": 0.05}),
                "pitch": ("FLOAT", {"default": 0.0, "min": -12.0, "max": 12.0, "step": 0.5}),
            },
            "optional": {
                "voice_name": ("STRING", {"forceInput": True}),
            },
        }

    RETURN_TYPES = ("AUDIO",)
    RETURN_NAMES = ("AUDIO",)
    FUNCTION = "generate"
    CATEGORY = "mock"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        # Always regenerate so each scene gets a fresh mock tone, even when the
        # inputs happen to be identical across loop iterations.
        return float("nan")

    @staticmethod
    def _resolve_voice(voice, voice_name):
        candidate = (voice_name or "").strip()
        if not candidate:
            return voice
        if candidate in KOKORO_VOICES:
            return candidate
        # Reuse the real mapper so friendly/child/legacy names behave the same
        # here as they do in KokoroSceneAudio.
        from .string_to_kokoro_voice import resolve
        resolved_voice, _pitch = resolve(candidate)
        return resolved_voice

    def generate(self, text, voice, speed, pitch=0.0, voice_name=None):
        resolved = self._resolve_voice(voice, voice_name)

        clean_text = (text or "").strip()
        if not clean_text:
            waveform = torch.zeros(1, 1, SAMPLE_RATE // 2)
            print("[MockSceneAudio] empty text -> 0.5s silence")
            return ({"waveform": waveform, "sample_rate": SAMPLE_RATE},)

        # Estimate duration the same way real narration roughly scales: about
        # 15 characters per second, adjusted by speed.
        chars = max(1, len(clean_text))
        seconds = max(0.5, (chars / 15.0) / max(0.1, float(speed)))
        num_samples = int(seconds * SAMPLE_RATE)

        # Voice-dependent base pitch, then apply the semitone `pitch` control
        # exactly like a real pitch shift would raise/lower the voice.
        freq = _base_freq(resolved) * (2.0 ** (float(pitch) / 12.0))
        # A little per-call jitter so repeated scenes are not identical.
        freq *= 1.0 + (random.Random(os.urandom(8)).random() - 0.5) * 0.06

        t = torch.linspace(0.0, seconds, num_samples)
        tone = 0.30 * torch.sin(2.0 * torch.pi * freq * t)
        tone += 0.12 * torch.sin(2.0 * torch.pi * freq * 1.5 * t)  # add a fifth

        # Short fade in/out to avoid clicks at the edges.
        fade = min(int(0.02 * SAMPLE_RATE), num_samples // 2)
        if fade > 0:
            ramp = torch.linspace(0.0, 1.0, fade)
            tone[:fade] *= ramp
            tone[-fade:] *= ramp.flip(0)

        waveform = tone.unsqueeze(0).unsqueeze(0)  # [1, 1, N]

        print(
            f"[MockSceneAudio] voice={resolved} speed={speed} pitch={pitch:+.1f}st "
            f"freq={freq:.0f}Hz sr={SAMPLE_RATE} duration={seconds:.2f}s "
            f"text[:60]={clean_text[:60]!r}"
        )
        return ({"waveform": waveform, "sample_rate": SAMPLE_RATE},)


NODE_CLASS_MAPPINGS = {
    "MockSceneAudio": MockSceneAudio,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MockSceneAudio": "Mock Scene Audio",
}
