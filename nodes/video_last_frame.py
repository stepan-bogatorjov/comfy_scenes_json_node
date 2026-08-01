import os
import re
import shutil
import subprocess

import numpy as np
import torch
from PIL import Image, ImageOps

import folder_paths

# Scene videos are named "<scene>_<counter>.mp4" (same scheme as the compile
# node). During a run they live directly in the output dir; once archived they
# sit inside a per-run subfolder.
SCENE_RE = re.compile(r"^(\d+)_(\d+)\.mp4$", re.IGNORECASE)


def _get_ffmpeg_exe() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as e:
        raise RuntimeError(
            "ffmpeg not found. Install it system-wide or run: pip install imageio-ffmpeg"
        ) from e


def _resolve_folder(base_dir: str, sub: str) -> str:
    """Join a user-supplied subfolder onto base_dir; empty -> base_dir itself.
    Matches StoryFinalCompile's scenes_folder handling."""
    if not sub or not sub.strip():
        return base_dir
    return os.path.join(base_dir, *sub.replace("\\", "/").strip("/").split("/"))


def _find_scene_video(scenes_dir: str, scene_num: int) -> str:
    """Path of the video for `scene_num` ("<scene>_<counter>.mp4"), highest
    counter wins. '' if the folder has none for that scene."""
    best = None  # (counter, path)
    if not os.path.isdir(scenes_dir):
        return ""
    for fname in os.listdir(scenes_dir):
        match = SCENE_RE.match(fname)
        if not match or int(match.group(1)) != scene_num:
            continue
        counter = int(match.group(2))
        if best is None or counter > best[0]:
            best = (counter, os.path.join(scenes_dir, fname))
    return best[1] if best else ""


class VideoLastFrame:
    """Extract the last frame of a scene video as an IMAGE.

    Given an `index` (scene number) and a `scenes_folder` relative to the
    ComfyUI output dir (same convention as StoryFinalCompile), locate the
    matching "<index>_<counter>.mp4" and decode its final frame, returning it
    downstream as a standard ComfyUI IMAGE tensor.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "index": ("INT", {"default": 1, "min": 0, "max": 999999}),
            },
            "optional": {
                "scenes_folder": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "video_path")
    FUNCTION = "extract"
    CATEGORY = "image"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def extract(self, index, scenes_folder=""):
        output_dir = folder_paths.get_output_directory()
        scenes_dir = _resolve_folder(output_dir, scenes_folder)

        video_path = _find_scene_video(scenes_dir, int(index))
        if not video_path:
            raise FileNotFoundError(
                f"[VideoLastFrame] No video matching '{int(index)}_<n>.mp4' in {scenes_dir}"
            )

        ffmpeg = _get_ffmpeg_exe()
        tmp_png = os.path.join(
            output_dir, f".lastframe_{int(index)}_{os.getpid()}.png"
        )
        try:
            # Seek to the last few seconds and keep overwriting the single
            # output frame (-update 1); the file left on disk is the final
            # decoded frame. NOTE: do NOT add "-frames:v 1" here - combined with
            # -sseof it stops after the FIRST frame past the seek point (and for
            # clips shorter than the seek window that is the very first frame of
            # the video), which is the opposite of what we want. Letting every
            # frame overwrite the same file leaves the true last frame.
            result = subprocess.run(
                [ffmpeg, "-y", "-nostdin", "-sseof", "-3", "-i", video_path,
                 "-update", "1", "-q:v", "1", tmp_png],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            if result.returncode != 0 or not os.path.exists(tmp_png):
                raise RuntimeError(
                    f"[VideoLastFrame] ffmpeg failed extracting last frame of "
                    f"{video_path} (exit {result.returncode}):\n{result.stderr[-1500:]}"
                )

            img = ImageOps.exif_transpose(Image.open(tmp_png)).convert("RGB")
            rgb = np.array(img).astype(np.float32) / 255.0
            image = torch.from_numpy(rgb)[None,]
        finally:
            if os.path.exists(tmp_png):
                try:
                    os.remove(tmp_png)
                except OSError:
                    pass

        print(f"[VideoLastFrame] scene {int(index)} last frame from "
              f"{os.path.basename(video_path)} ({image.shape[2]}x{image.shape[1]})")
        return (image, video_path)


NODE_CLASS_MAPPINGS = {
    "VideoLastFrame": VideoLastFrame,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "VideoLastFrame": "Video Last Frame",
}
