import os
import folder_paths


class SaveVideoPassthrough:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("VIDEO",),
                "filename_prefix": ("STRING", {"default": "scene"}),
            }
        }

    RETURN_TYPES = ("VIDEO",)
    RETURN_NAMES = ("video",)
    FUNCTION = "save_and_return"
    CATEGORY = "video"

    def save_and_return(self, video, filename_prefix):
        output_dir = folder_paths.get_output_directory()

        subfolder = ""
        clean_prefix = filename_prefix

        if "/" in filename_prefix or "\\" in filename_prefix:
            clean_prefix = filename_prefix.replace("\\", "/")
            parts = clean_prefix.split("/")
            subfolder = "/".join(parts[:-1])
            clean_prefix = parts[-1]
            output_dir = os.path.join(output_dir, subfolder)

        os.makedirs(output_dir, exist_ok=True)

        counter = 1
        while True:
            filename = f"{clean_prefix}_{counter:05d}.mp4"
            full_path = os.path.join(output_dir, filename)
            if not os.path.exists(full_path):
                break
            counter += 1

        print(f"[SaveVideoPassthrough] saving to: {full_path}")

        video.save_to(full_path)

        return (video,)


NODE_CLASS_MAPPINGS = {
    "SaveVideoPassthrough": SaveVideoPassthrough,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SaveVideoPassthrough": "Save Video Passthrough",
}
