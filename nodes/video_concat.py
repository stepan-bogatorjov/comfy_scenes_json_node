"""StoryVideoConcat — ComfyUI node that merges all scene videos into one final video.

Uses ffmpeg's xfade filter to chain scene videos with a smooth transition
(dissolve, fade, etc.) between each scene. Audio tracks are crossfaded
via acrossfade for seamless transitions.

Scene count, durations, and filename pattern are all derived from the
story JSON — no manual configuration needed.
"""

import glob
import os
import re
import shutil
import subprocess
import unicodedata

from ..utils.json_parser import load_story_json


TRANSITIONS = [
    "fade", "fadeblack", "fadewhite", "dissolve",
    "wipeleft", "wiperight", "wipeup", "wipedown",
    "slideleft", "slideright", "slideup", "slidedown",
    "circlecrop", "circleopen", "circleclose",
    "radial", "smoothleft", "smoothright", "smoothup", "smoothdown",
    "pixelize", "hlslice", "vlslice", "hrslice", "vrslice",
    "hblur", "fadegrays", "distance", "squeezev", "squeezeh",
]


def _get_ffmpeg_exe() -> str:
    """Locate the ffmpeg executable. Tries PATH first, then imageio-ffmpeg."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as e:
        raise RuntimeError(
            "ffmpeg not found. Install it system-wide or run: "
            "pip install imageio-ffmpeg"
        ) from e


def _sanitize_title(title: str) -> str:
    """Match the logic in StorySceneFilename — keep consistent."""
    normalized = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    lowered = normalized.lower().strip()
    cleaned = re.sub(r"[^a-z0-9]+", "_", lowered)
    return cleaned.strip("_")


def _find_scene_videos(folder: str, title_slug: str, scene_count: int) -> tuple[list[str], list[int]]:
    """Find scene videos matching the filename pattern, sorted by scene number.

    Returns (ordered_filepaths, missing_scene_numbers). Does not raise on missing.
    """
    pattern = os.path.join(folder, f"{title_slug}_scene_*.mp4")
    all_files = glob.glob(pattern)

    # Map: scene_number -> filepath
    by_scene = {}
    scene_num_re = re.compile(rf"{re.escape(title_slug)}_scene_(\d+)")
    for filepath in all_files:
        match = scene_num_re.search(os.path.basename(filepath))
        if match:
            scene_num = int(match.group(1))
            # If multiple files exist for the same scene, keep the latest
            if scene_num not in by_scene or filepath > by_scene[scene_num]:
                by_scene[scene_num] = filepath

    missing = []
    ordered = []
    for i in range(1, scene_count + 1):
        if i not in by_scene:
            missing.append(i)
        else:
            ordered.append(by_scene[i])

    return ordered, missing


def _build_filter_complex(durations: list[int], transition: str, trans_dur: float) -> str:
    """Build ffmpeg filter_complex string for chained xfade + acrossfade.

    For N videos, chains N-1 transitions. Each xfade offset is the cumulative
    duration up to that point minus the transition count times transition duration.
    """
    n = len(durations)
    if n < 2:
        return ""

    parts = []
    # Video chain
    prev_v = "[0:v]"
    cum = 0.0
    for i in range(1, n):
        cum += durations[i - 1]
        offset = cum - i * trans_dur
        out_label = f"[v{i}]" if i < n - 1 else "[vout]"
        parts.append(
            f"{prev_v}[{i}:v]xfade=transition={transition}:"
            f"duration={trans_dur}:offset={offset:.3f}{out_label}"
        )
        prev_v = out_label

    # Audio chain (crossfade at each boundary)
    prev_a = "[0:a]"
    for i in range(1, n):
        out_label = f"[a{i}]" if i < n - 1 else "[aout]"
        parts.append(f"{prev_a}[{i}:a]acrossfade=d={trans_dur}{out_label}")
        prev_a = out_label

    return ";".join(parts)


class StoryVideoConcat:
    """Concatenate all scene videos into a single final video with transitions."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_folder": ("STRING", {"default": ""}),
                "transition": (TRANSITIONS, {"default": "fade"}),
                "transition_duration": ("FLOAT", {"default": 0.2, "min": 0.0, "max": 3.0, "step": 0.05}),
            },
            "optional": {
                "title": ("STRING", {"default": ""}),
                "output_filename": ("STRING", {"default": ""}),
                "json_text": ("STRING", {"multiline": True, "default": ""}),
                "file_path": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ()
    OUTPUT_NODE = True
    FUNCTION = "concat"
    CATEGORY = "ViralStory"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def concat(self, video_folder, transition, transition_duration,
               title="", output_filename="", json_text="", file_path=""):
        if not video_folder.strip():
            raise ValueError("StoryVideoConcat: 'video_folder' is required")

        if not os.path.isdir(video_folder):
            raise ValueError(f"StoryVideoConcat: video_folder does not exist: {video_folder}")

        story = load_story_json(json_text, file_path)
        scenes = story["scenes"]
        scene_count = len(scenes)
        durations = [int(s["duration"]) for s in scenes]

        # Auto-fill title from the story JSON if not provided
        effective_title = title.strip() or str(story.get("title", ""))
        if not effective_title:
            raise ValueError("StoryVideoConcat: no title found in input or story JSON")

        title_slug = _sanitize_title(effective_title)

        videos, missing = _find_scene_videos(video_folder, title_slug, scene_count)
        if missing:
            raise FileNotFoundError(
                f"StoryVideoConcat: missing scene videos {missing} in {video_folder} "
                f"(pattern: {title_slug}_scene_XX*.mp4)"
            )

        out_name = output_filename.strip() or f"{title_slug}_final.mp4"
        if not out_name.lower().endswith(".mp4"):
            out_name += ".mp4"
        out_path = os.path.join(video_folder, out_name)

        ffmpeg = _get_ffmpeg_exe()
        cmd = [ffmpeg, "-y"]
        for v in videos:
            cmd += ["-i", v]

        filter_complex = _build_filter_complex(durations, transition, transition_duration)
        if filter_complex:
            cmd += ["-filter_complex", filter_complex,
                    "-map", "[vout]", "-map", "[aout]"]
        # else: single scene, just copy

        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", out_path]

        print(f"[StoryVideoConcat] Merging {scene_count} scenes with '{transition}' transition...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg failed (exit {result.returncode}):\n{result.stderr[-2000:]}"
            )

        print(f"[StoryVideoConcat] Saved: {out_path}")
        return {}
