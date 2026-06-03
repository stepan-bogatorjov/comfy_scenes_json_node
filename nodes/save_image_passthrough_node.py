import os

import numpy as np
from PIL import Image

import folder_paths


class SaveImagePassthrough:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "filename_prefix": ("STRING", {"default": "scene"}),
                "output_folder": ("STRING", {"default": ""}),
                "add_counter": ("BOOLEAN", {"default": True}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    FUNCTION = "save_and_return"
    CATEGORY = "image"

    def save_and_return(self, image, filename_prefix, output_folder="", add_counter=True):
        output_dir = folder_paths.get_output_directory()
        if output_folder.strip():
            output_dir = os.path.join(output_dir, *output_folder.replace("\\", "/").strip("/").split("/"))

        clean_prefix = filename_prefix
        if "/" in filename_prefix or "\\" in filename_prefix:
            clean_prefix = filename_prefix.replace("\\", "/")
            parts = clean_prefix.split("/")
            subfolder = "/".join(parts[:-1])
            clean_prefix = parts[-1]
            output_dir = os.path.join(output_dir, subfolder)

        os.makedirs(output_dir, exist_ok=True)

        counter = 1
        multiple = len(image) > 1
        for idx, frame in enumerate(image):
            if add_counter:
                while True:
                    filename = f"{clean_prefix}_{counter:05d}.png"
                    full_path = os.path.join(output_dir, filename)
                    if not os.path.exists(full_path):
                        break
                    counter += 1
            else:
                suffix = f"_{idx + 1}" if multiple else ""
                filename = f"{clean_prefix}{suffix}.png"
                full_path = os.path.join(output_dir, filename)

            arr = (frame.cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
            Image.fromarray(arr).save(full_path)
            print(f"[SaveImagePassthrough] saving to: {full_path}")
            counter += 1

        return (image,)


NODE_CLASS_MAPPINGS = {
    "SaveImagePassthrough": SaveImagePassthrough,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SaveImagePassthrough": "Save Image Passthrough",
}
