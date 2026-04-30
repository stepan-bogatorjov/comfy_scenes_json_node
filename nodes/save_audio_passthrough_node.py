import os
import wave

import torch

import folder_paths


class SaveAudioPassthrough:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
                "filename_prefix": ("STRING", {"default": "scene"}),
            }
        }

    RETURN_TYPES = ("AUDIO",)
    RETURN_NAMES = ("audio",)
    FUNCTION = "save_and_return"
    CATEGORY = "audio"

    def save_and_return(self, audio, filename_prefix):
        output_dir = folder_paths.get_output_directory()

        clean_prefix = filename_prefix
        if "/" in filename_prefix or "\\" in filename_prefix:
            clean_prefix = filename_prefix.replace("\\", "/")
            parts = clean_prefix.split("/")
            subfolder = "/".join(parts[:-1])
            clean_prefix = parts[-1]
            output_dir = os.path.join(output_dir, subfolder)

        os.makedirs(output_dir, exist_ok=True)

        waveform = audio["waveform"]
        sample_rate = int(audio["sample_rate"])

        if waveform.dim() == 3:
            batch = waveform
        elif waveform.dim() == 2:
            batch = waveform.unsqueeze(0)
        else:
            batch = waveform.view(1, 1, -1)

        counter = 1
        for clip in batch:
            while True:
                filename = f"{clean_prefix}_{counter:05d}.wav"
                full_path = os.path.join(output_dir, filename)
                if not os.path.exists(full_path):
                    break
                counter += 1

            tensor = clip.detach().cpu().to(torch.float32).clamp_(-1.0, 1.0)
            channels = tensor.shape[0]
            interleaved = tensor.transpose(0, 1).contiguous()
            pcm16 = (interleaved * 32767.0).to(torch.int16).numpy()

            with wave.open(full_path, "wb") as wf:
                wf.setnchannels(channels)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(pcm16.tobytes())

            print(f"[SaveAudioPassthrough] saving to: {full_path}")
            counter += 1

        return (audio,)


NODE_CLASS_MAPPINGS = {
    "SaveAudioPassthrough": SaveAudioPassthrough,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SaveAudioPassthrough": "Save Audio Passthrough",
}
