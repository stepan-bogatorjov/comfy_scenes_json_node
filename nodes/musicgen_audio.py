"""Local (offline, free) text-to-music generation using Meta MusicGen.

Same spirit as KokoroSceneAudio: a prompt goes in, a ComfyUI AUDIO dict comes
out ({"waveform": [1, C, N], "sample_rate": int}), so it drops straight into the
story pipeline (background music for StoryFinalCompile).

MusicGen is trained on 30 s windows, so anything longer is produced by
audio-prompted continuation: generate a window, feed its tail back as an audio
prompt, keep only the newly generated part, repeat until the requested length is
reached. Weights are fp16 on CUDA; `musicgen-small` needs ~1 GB VRAM and
`musicgen-medium` ~3.5 GB, both comfortable on an 8 GB laptop 4060.
"""

import gc

import torch

MODELS = [
    "facebook/musicgen-small",          # 300M, mono, fastest
    "facebook/musicgen-medium",         # 1.5B, mono, better musicality
    "facebook/musicgen-stereo-small",   # 300M, stereo
    "facebook/musicgen-stereo-medium",  # 1.5B, stereo
]

FRAME_RATE = 50            # MusicGen produces 50 audio tokens per second
MAX_WINDOW_SECONDS = 30.0  # training window; longer output is stitched
CONTINUATION_PROMPT_SECONDS = 5.0  # tail fed back as the audio prompt

# Lazily-loaded model cache, keyed by repo id.
_MODELS = {}


def _device():
    return "cuda" if torch.cuda.is_available() else "cpu"


def _get_model(repo_id):
    """Return a cached (processor, model) pair, loading it once per repo id."""
    entry = _MODELS.get(repo_id)
    if entry is None:
        from transformers import AutoProcessor, MusicgenForConditionalGeneration

        device = _device()
        dtype = torch.float16 if device == "cuda" else torch.float32
        processor = AutoProcessor.from_pretrained(repo_id)
        try:
            model = MusicgenForConditionalGeneration.from_pretrained(repo_id, dtype=dtype)
        except TypeError:
            # transformers < 5 spells it torch_dtype.
            model = MusicgenForConditionalGeneration.from_pretrained(repo_id, torch_dtype=dtype)
        model = model.to(device).eval()
        entry = (processor, model)
        _MODELS[repo_id] = entry
        print(f"[MusicGenAudio] loaded {repo_id} on {device} ({dtype})")
    return entry


def _unload_all():
    _MODELS.clear()
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


class MusicGenAudio:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "multiline": True,
                    "default": "warm cinematic lo-fi piano, soft strings, gentle heartbeat, calm bedtime story mood",
                }),
                "duration_seconds": ("FLOAT", {"default": 15.0, "min": 1.0, "max": 300.0, "step": 0.5}),
                "model": (MODELS, {"default": "facebook/musicgen-small"}),
                # Classifier-free guidance: how hard to follow the prompt.
                "guidance_scale": ("FLOAT", {"default": 3.0, "min": 1.0, "max": 10.0, "step": 0.1}),
                "temperature": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 2.0, "step": 0.05}),
                "top_k": ("INT", {"default": 250, "min": 0, "max": 1000}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFF}),
                "fade_out_seconds": ("FLOAT", {"default": 1.5, "min": 0.0, "max": 10.0, "step": 0.1}),
                # Keeping the model resident is faster across scenes, but the
                # 8 GB laptop GPU usually wants that VRAM back for video gen.
                "keep_model_loaded": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                # Lets the prompt (or a per-scene music cue) arrive from the story JSON.
                "prompt_override": ("STRING", {"forceInput": True}),
            },
        }

    RETURN_TYPES = ("AUDIO", "FLOAT")
    RETURN_NAMES = ("AUDIO", "duration_seconds")
    FUNCTION = "generate"
    CATEGORY = "audio"

    @staticmethod
    def _generate_window(processor, model, text, new_tokens, gen_kwargs, audio_prompt, sample_rate):
        """Generate `new_tokens` worth of audio, optionally continuing `audio_prompt`.

        Returns only the newly generated tail as a [C, N] float32 CPU tensor.
        """
        device = model.device
        if audio_prompt is None:
            inputs = processor(text=[text], padding=True, return_tensors="pt")
        else:
            # processor expects mono float audio; average channels for the prompt.
            prompt_mono = audio_prompt.mean(dim=0).numpy()
            inputs = processor(
                text=[text],
                audio=prompt_mono,
                sampling_rate=sample_rate,
                padding=True,
                return_tensors="pt",
            )
        # Move to the model's device; float tensors (the audio prompt) must also
        # match the model dtype, otherwise the fp16 encoder rejects fp32 input.
        moved = {}
        for key, value in inputs.items():
            if hasattr(value, "to"):
                value = value.to(device)
                if torch.is_floating_point(value):
                    value = value.to(model.dtype)
            moved[key] = value
        inputs = moved

        with torch.no_grad():
            values = model.generate(**inputs, max_new_tokens=int(new_tokens), **gen_kwargs)

        wav = values[0].detach().to("cpu").float()  # [C, N]
        expected = int(new_tokens) * (sample_rate // FRAME_RATE)
        if wav.shape[-1] > expected:
            # Audio-prompted output includes the prompt; drop it.
            wav = wav[..., -expected:]
        return wav

    def generate(self, prompt, duration_seconds, model, guidance_scale, temperature,
                 top_k, seed, fade_out_seconds, keep_model_loaded, prompt_override=None):
        text = (prompt_override or "").strip() or (prompt or "").strip()
        if not text:
            text = "soft ambient background music"

        processor, mg = _get_model(model)
        sample_rate = mg.config.audio_encoder.sampling_rate
        samples_per_token = sample_rate // FRAME_RATE

        gen_kwargs = {
            "do_sample": True,
            "guidance_scale": float(guidance_scale),
            "temperature": float(temperature),
        }
        if int(top_k) > 0:
            gen_kwargs["top_k"] = int(top_k)

        torch.manual_seed(int(seed))
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(int(seed))

        total_tokens = max(1, int(round(float(duration_seconds) * FRAME_RATE)))
        window_tokens = int(MAX_WINDOW_SECONDS * FRAME_RATE)
        prompt_tokens = int(CONTINUATION_PROMPT_SECONDS * FRAME_RATE)

        chunks = []
        produced = 0
        while produced < total_tokens:
            remaining = total_tokens - produced
            if not chunks:
                new_tokens = min(remaining, window_tokens)
                audio_prompt = None
            else:
                # Leave room for the audio prompt inside the 30 s window.
                new_tokens = min(remaining, window_tokens - prompt_tokens)
                tail_samples = prompt_tokens * samples_per_token
                audio_prompt = torch.cat(chunks, dim=-1)[..., -tail_samples:]
            chunk = self._generate_window(
                processor, mg, text, new_tokens, gen_kwargs, audio_prompt, sample_rate
            )
            chunks.append(chunk)
            produced += new_tokens
            if len(chunks) > 1 or total_tokens > window_tokens:
                print(f"[MusicGenAudio] {produced / FRAME_RATE:.1f}s / "
                      f"{total_tokens / FRAME_RATE:.1f}s generated")

        wav = torch.cat(chunks, dim=-1)
        target_samples = int(round(float(duration_seconds) * sample_rate))
        if wav.shape[-1] > target_samples:
            wav = wav[..., :target_samples]

        fade = int(min(float(fade_out_seconds), wav.shape[-1] / sample_rate) * sample_rate)
        if fade > 1:
            wav[..., -fade:] *= torch.linspace(1.0, 0.0, fade)

        peak = float(wav.abs().max())
        if peak > 1.0:
            wav = wav / peak * 0.98

        if not keep_model_loaded:
            _unload_all()

        duration = wav.shape[-1] / sample_rate
        print(f"[MusicGenAudio] model={model} sr={sample_rate} ch={wav.shape[0]} "
              f"duration={duration:.2f}s prompt[:70]={text[:70]!r}")
        return ({"waveform": wav.unsqueeze(0), "sample_rate": sample_rate}, duration)


NODE_CLASS_MAPPINGS = {
    "MusicGenAudio": MusicGenAudio,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MusicGenAudio": "MusicGen Audio (local music)",
}
