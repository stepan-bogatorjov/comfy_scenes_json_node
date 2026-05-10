import glob
import os
import re
import shutil
import subprocess

import folder_paths


class _AnyType(str):
    def __ne__(self, other):
        return False

    def __eq__(self, other):
        return True

    def __hash__(self):
        return id(self)


ANY = _AnyType("*")

SCENE_RE = re.compile(r"^(\d+)_(\d+)\.mp4$", re.IGNORECASE)
VOICEOVER_EXTS = ("mp3", "wav", "flac", "m4a", "aac", "ogg")


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


def _probe_duration(ffmpeg_path: str, file_path: str) -> float:
    result = subprocess.run(
        [ffmpeg_path, "-i", file_path, "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    match = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", result.stderr)
    if not match:
        raise RuntimeError(
            f"Could not probe duration of {file_path}\n{result.stderr[-800:]}"
        )
    h, m, s = match.groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


def _atempo_chain(tempo: float) -> str:
    parts = []
    safe_tempo = max(tempo, 1e-6)
    while safe_tempo < 0.5:
        parts.append("atempo=0.5")
        safe_tempo /= 0.5
    while safe_tempo > 100.0:
        parts.append("atempo=100.0")
        safe_tempo /= 100.0
    parts.append(f"atempo={safe_tempo:.6f}")
    return ",".join(parts)


def _find_scene_videos(output_dir: str) -> list[str]:
    by_scene: dict[int, tuple[int, str]] = {}
    for fname in os.listdir(output_dir):
        match = SCENE_RE.match(fname)
        if not match:
            continue
        scene_num = int(match.group(1))
        counter = int(match.group(2))
        full = os.path.join(output_dir, fname)
        if scene_num not in by_scene or by_scene[scene_num][0] < counter:
            by_scene[scene_num] = (counter, full)
    return [by_scene[k][1] for k in sorted(by_scene.keys())]


def _find_voiceover(output_dir: str) -> str | None:
    candidates = []
    for ext in VOICEOVER_EXTS:
        candidates.extend(glob.glob(os.path.join(output_dir, f"voiceover_*.{ext}")))
    if not candidates:
        return None
    return max(candidates, key=os.path.getmtime)


class StoryFinalCompile:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "trigger": (ANY, {}),
            },
            "optional": {
                "transition_duration": ("FLOAT", {"default": 0.2, "min": 0.0, "max": 2.0, "step": 0.05}),
                "filename_prefix": ("STRING", {"default": "final"}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("output_path",)
    FUNCTION = "compile"
    CATEGORY = "video"
    OUTPUT_NODE = True

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def compile(self, trigger, transition_duration=0.2, filename_prefix="final"):
        output_dir = folder_paths.get_output_directory()

        videos = _find_scene_videos(output_dir)
        if not videos:
            raise FileNotFoundError(
                f"[StoryFinalCompile] No scene videos matching '<n>_<n>.mp4' in {output_dir}"
            )

        voiceover = _find_voiceover(output_dir)
        if not voiceover:
            raise FileNotFoundError(
                f"[StoryFinalCompile] No 'voiceover_*' audio file found in {output_dir}"
            )

        ffmpeg = _get_ffmpeg_exe()
        v_durations = [_probe_duration(ffmpeg, v) for v in videos]
        a_duration = _probe_duration(ffmpeg, voiceover)

        n = len(videos)
        trans = float(transition_duration) if n > 1 else 0.0
        final_video_dur = sum(v_durations) - (n - 1) * trans

        tempo = a_duration / final_video_dur if final_video_dur > 0 else 1.0
        atempo = _atempo_chain(tempo)

        counter = 1
        while True:
            out_name = f"{filename_prefix}_{counter:05d}.mp4"
            out_path = os.path.join(output_dir, out_name)
            if not os.path.exists(out_path):
                break
            counter += 1

        cmd = [ffmpeg, "-y"]
        for v in videos:
            cmd += ["-i", v]
        cmd += ["-i", voiceover]
        audio_idx = n

        if n > 1:
            parts = []
            prev = "[0:v]"
            cum = 0.0
            for i in range(1, n):
                cum += v_durations[i - 1]
                offset = cum - i * trans
                out_label = f"[v{i}]" if i < n - 1 else "[vout]"
                parts.append(
                    f"{prev}[{i}:v]xfade=transition=fade:"
                    f"duration={trans}:offset={offset:.3f}{out_label}"
                )
                prev = out_label
            parts.append(f"[{audio_idx}:a]{atempo}[aout]")
            filter_complex = ";".join(parts)
            cmd += [
                "-filter_complex", filter_complex,
                "-map", "[vout]", "-map", "[aout]",
            ]
        else:
            filter_complex = f"[{audio_idx}:a]{atempo}[aout]"
            cmd += [
                "-filter_complex", filter_complex,
                "-map", "0:v", "-map", "[aout]",
            ]

        cmd += [
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", out_path,
        ]

        print(f"[StoryFinalCompile] scenes={n} videos={[os.path.basename(v) for v in videos]}")
        print(f"[StoryFinalCompile] voiceover={os.path.basename(voiceover)}")
        print(
            f"[StoryFinalCompile] video_dur={final_video_dur:.2f}s "
            f"audio_dur={a_duration:.2f}s tempo={tempo:.4f}"
        )
        print(f"[StoryFinalCompile] -> {out_path}")

        result = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"[StoryFinalCompile] ffmpeg failed (exit {result.returncode}):\n"
                f"{result.stderr[-2000:]}"
            )

        return (out_path,)


NODE_CLASS_MAPPINGS = {
    "StoryFinalCompile": StoryFinalCompile,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "StoryFinalCompile": "Story Final Compile",
}
