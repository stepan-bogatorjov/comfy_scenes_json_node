import os

import folder_paths


class SaveTextPassthrough:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"forceInput": True}),
                "filename_prefix": ("STRING", {"default": "scene"}),
                "output_folder": ("STRING", {"default": ""}),
                "extension": ("STRING", {"default": "txt"}),
                "add_counter": ("BOOLEAN", {"default": True}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "save_and_return"
    CATEGORY = "text"

    def save_and_return(self, text, filename_prefix, output_folder="", extension="txt", add_counter=True):
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

        ext = (extension or "txt").lstrip(".") or "txt"

        if add_counter:
            counter = 1
            while True:
                filename = f"{clean_prefix}_{counter:05d}.{ext}"
                full_path = os.path.join(output_dir, filename)
                if not os.path.exists(full_path):
                    break
                counter += 1
        else:
            filename = f"{clean_prefix}.{ext}"
            full_path = os.path.join(output_dir, filename)

        with open(full_path, "w", encoding="utf-8") as f:
            f.write(text)

        print(f"[SaveTextPassthrough] saving to: {full_path}")

        return (text,)


NODE_CLASS_MAPPINGS = {
    "SaveTextPassthrough": SaveTextPassthrough,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SaveTextPassthrough": "Save Text Passthrough",
}
