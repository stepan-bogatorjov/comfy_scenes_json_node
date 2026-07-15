"""Map a friendly voice name to a Kokoro voice id (+ pitch shift).

The story JSON picks a voice by a short human-readable name in
scenes[n].voiceover.type. This node translates that name into the concrete
Kokoro voice id AND a pitch shift in semitones, so a single name can also
describe "child" voices (a light Kokoro voice pitched up).

Outputs:
    voice  (STRING) -> wire into KokoroSceneAudio.voice_name
    pitch  (FLOAT)  -> wire into KokoroSceneAudio.pitch

Resolution order for the incoming name:
    1. a curated friendly name (see CURATED below)  -> its (voice, pitch)
    2. a raw kokoro id (e.g. "af_heart")            -> pass through, pitch 0
    3. a legacy ElevenLabs-style name               -> LEGACY map, pitch 0
    4. anything else                                -> DEFAULT_VOICE, pitch 0
"""

# --- Curated "best" voices exposed to the story generator -----------------
# name -> (kokoro_voice_id, pitch_semitones, human description)
CURATED = {
    # Female (American)
    "Heart":   ("af_heart", 0.0,  "warm, natural female narrator - highest quality, default choice"),
    "Bella":   ("af_bella", 0.0,  "expressive, energetic female - great for lively, upbeat stories"),
    "Nicole":  ("af_nicole", 0.0, "soft, gentle, intimate female - close, cozy narration"),
    "Aoede":   ("af_aoede", 0.0,  "calm, neutral female - steady, easygoing narration"),
    "Sarah":   ("af_sarah", 0.0,  "clear, neutral female documentary-style narrator"),
    # Male (American)
    "Michael": ("am_michael", 0.0, "warm, friendly male narrator - reliable default male voice"),
    "Fenrir":  ("am_fenrir", 0.0,  "deep, serious male - suspense, tension, dramatic scenes"),
    "Puck":    ("am_puck", 0.0,    "lively, playful male - comedy and cheerful cartoon energy"),
    # British
    "Emma":    ("bf_emma", 0.0,    "warm British female - the best-sounding UK voice"),
    "George":  ("bm_george", 0.0,  "classic British male storyteller narrator"),
    "Fable":   ("bm_fable", 0.0,   "British male fairy-tale / bedtime-story teller"),
    # Childlike (light voice pitched up; duration preserved)
    "Child":       ("af_sky", 6.0,   "bright, cheerful childlike voice (girl/androgynous kid)"),
    "ChildWarm":   ("af_heart", 5.0, "warm, soft childlike voice - cleanest child timbre"),
    "ChildBritish":("bf_lily", 6.0,  "little British child voice"),
}

# --- Legacy ElevenLabs-style names (backwards compatibility) ---------------
LEGACY = {
    "Roger": "am_onyx", "Laura": "af_aoede", "River": "af_river", "Alice": "bf_alice",
    "Matilda": "af_kore", "Jessica": "af_jessica", "Lily": "bf_lily", "Charlie": "am_puck",
    "Callum": "am_fenrir", "Harry": "am_echo", "Liam": "am_liam", "Will": "am_michael",
    "Eric": "am_eric", "Chris": "bm_lewis", "Brian": "am_santa", "Daniel": "bm_daniel",
    "Adam": "am_adam", "Bill": "am_onyx",
}

DEFAULT_VOICE = "am_michael"

# Full list of valid Kokoro ids (kept in one place for validation).
from .kokoro_scene_audio import KOKORO_VOICES


def resolve(name):
    """Return (voice_id, pitch_semitones) for a friendly/raw/legacy name."""
    clean = (name or "").strip()
    if clean in CURATED:
        voice, pitch, _desc = CURATED[clean]
        return voice, pitch
    if clean in KOKORO_VOICES:
        return clean, 0.0
    if clean in LEGACY:
        return LEGACY[clean], 0.0
    # case-insensitive curated match as a convenience
    for key, (voice, pitch, _d) in CURATED.items():
        if key.lower() == clean.lower():
            return voice, pitch
    return DEFAULT_VOICE, 0.0


class StringToKokoroVoice:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "name": ("STRING", {"default": "Heart", "forceInput": False}),
            }
        }

    RETURN_TYPES = ("STRING", "FLOAT")
    RETURN_NAMES = ("voice", "pitch")
    FUNCTION = "convert"
    CATEGORY = "audio"

    def convert(self, name):
        voice, pitch = resolve(name)
        print(f"[StringToKokoroVoice] name={(name or '').strip()!r} -> voice={voice!r} pitch={pitch:+.1f}")
        return (voice, pitch)


NODE_CLASS_MAPPINGS = {
    "StringToKokoroVoice": StringToKokoroVoice,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "StringToKokoroVoice": "String -> Kokoro Voice",
}
