VOICE_IDS = {
    "Roger": "CwhRBWXzGAHq8TQ4Fs17",
    "Sarah": "EXAVITQu4vr4xnSDxMaL",
    "Laura": "FGY2WhTYpPnrIDTdsKH5",
    "Charlie": "IKne3meq5aSn9XLyUdCD",
    "George": "JBFqnCBsd6RMkjVDRZzb",
    "Callum": "N2lVS1w4EtoT3dr4eOWO",
    "River": "SAz9YHcvj6GT2YYXdXww",
    "Harry": "SOYHLrjzK2X1ezoPC6cr",
    "Liam": "TX3LPaxmHKxFdv7VOQHJ",
    "Alice": "Xb7hH8MSUJpSbSDYk0k2",
    "Matilda": "XrExE9yKIg1WjnnlVkGX",
    "Will": "bIHbv24MWmeRgasZH58o",
    "Jessica": "cgSgspJ2msm6clMCkdW9",
    "Eric": "cjVigY5qzO86Huf0OWal",
    "Bella": "EXAVITQu4vr4xnSDxMaL",
    "Chris": "iP95p4xoKVk53GoZ742B",
    "Brian": "nPczCjzI2devNBz1zQrb",
    "Daniel": "onwK4e9ZLuTAKqWW03F9",
    "Lily": "pFZP5JQG7iQjIQuC4Bku",
    "Adam": "pNInz6obpgDQGcFmaJgB",
    "Bill": "pqHfZKP75CvOlQylNhV4",
}


class StringToElevenLabsVoice:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "name": ("STRING", {"default": "Roger", "forceInput": False}),
            }
        }

    RETURN_TYPES = ("ELEVENLABS_VOICE",)
    RETURN_NAMES = ("voice",)
    FUNCTION = "convert"
    CATEGORY = "audio"

    def convert(self, name):
        clean = (name or "").strip()
        voice_id = VOICE_IDS.get(clean, clean)
        print(f"[StringToElevenLabsVoice] name={clean!r} -> voice_id={voice_id!r}")
        return (voice_id,)


NODE_CLASS_MAPPINGS = {
    "StringToElevenLabsVoice": StringToElevenLabsVoice,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "StringToElevenLabsVoice": "String → ElevenLabs Voice",
}
