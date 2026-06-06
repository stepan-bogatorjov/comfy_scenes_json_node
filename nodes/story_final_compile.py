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
VOICE_RE = re.compile(
    r"^(\d+)_(\d+)\.(?:" + "|".join(VOICEOVER_EXTS) + r")$", re.IGNORECASE
)


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


def _resolve_folder(base_dir: str, sub: str) -> str:
    """Join a user-supplied subfolder onto base_dir; empty -> base_dir itself."""
    if not sub or not sub.strip():
        return base_dir
    return os.path.join(base_dir, *sub.replace("\\", "/").strip("/").split("/"))


def _find_scenes(scenes_dir: str) -> list[tuple[int, str]]:
    """Return [(scene_num, path), ...] sorted by scene_num. For duplicate scene
    numbers the highest counter wins."""
    by_scene: dict[int, tuple[int, str]] = {}
    if not os.path.isdir(scenes_dir):
        return []
    for fname in os.listdir(scenes_dir):
        match = SCENE_RE.match(fname)
        if not match:
            continue
        scene_num = int(match.group(1))
        counter = int(match.group(2))
        full = os.path.join(scenes_dir, fname)
        if scene_num not in by_scene or by_scene[scene_num][0] < counter:
            by_scene[scene_num] = (counter, full)
    return [(num, by_scene[num][1]) for num in sorted(by_scene.keys())]


def _find_scene_voiceovers(voiceover_dir: str) -> dict[int, str]:
    """Map scene_num -> voiceover path ('<scene>_<counter>.<ext>'), highest
    counter wins. Empty dict if the folder has no matching files."""
    by_scene: dict[int, tuple[int, str]] = {}
    if not os.path.isdir(voiceover_dir):
        return {}
    for fname in os.listdir(voiceover_dir):
        match = VOICE_RE.match(fname)
        if not match:
            continue
        scene_num = int(match.group(1))
        counter = int(match.group(2))
        full = os.path.join(voiceover_dir, fname)
        if scene_num not in by_scene or by_scene[scene_num][0] < counter:
            by_scene[scene_num] = (counter, full)
    return {num: by_scene[num][1] for num in by_scene}


class StoryFinalCompile:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "trigger": (ANY, {}),
            },
            "optional": {
                "scenes_folder": ("STRING", {"default": ""}),
                "voiceover_folder": ("STRING", {"default": ""}),
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

    def compile(self, trigger, scenes_folder="", voiceover_folder="",
                transition_duration=0.2, filename_prefix="final"):
        output_dir = folder_paths.get_output_directory()
        scenes_dir = _resolve_folder(output_dir, scenes_folder)
        voiceover_dir = _resolve_folder(output_dir, voiceover_folder)

        scenes = _find_scenes(scenes_dir)
        if not scenes:
            raise FileNotFoundError(
                f"[StoryFinalCompile] No scene videos matching '<n>_<n>.mp4' in {scenes_dir}"
            )

        scene_nums = [num for num, _ in scenes]
        videos = [path for _, path in scenes]
        voiceovers = _find_scene_voiceovers(voiceover_dir)

        ffmpeg = _get_ffmpeg_exe()
        v_durations = [_probe_duration(ffmpeg, v) for v in videos]

        n = len(videos)
        trans = float(transition_duration) if n > 1 else 0.0
        final_video_dur = sum(v_durations) - (n - 1) * trans

        # Timeline start of each scene, matching the xfade offsets below: every
        # transition overlaps the previous scene by `trans` seconds.
        starts = [0.0] * n
        cum = 0.0
        for i in range(1, n):
            cum += v_durations[i - 1]
            starts[i] = cum - i * trans

        # Match a voiceover to each scene by its number; retime it to that
        # scene's video length. Scenes without a file stay silent.
        audio_inputs = []  # (video_index, path, a_duration)
        for i in range(n):
            path = voiceovers.get(scene_nums[i])
            if path:
                audio_inputs.append((i, path, _probe_duration(ffmpeg, path)))

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
        for _, path, _ in audio_inputs:
            cmd += ["-i", path]

        parts = []

        # --- video: crossfade chain ---
        if n > 1:
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
            video_map = "[vout]"
        else:
            video_map = "0:v"

        # --- audio: each scene's voiceover retimed and placed on the timeline ---
        audio_labels = []
        for k, (i, _path, a_dur) in enumerate(audio_inputs):
            in_idx = n + k
            v_i = v_durations[i]
            tempo = a_dur / v_i if v_i > 0 else 1.0
            atempo = _atempo_chain(tempo)
            delay_ms = int(round(starts[i] * 1000))
            label = f"[a{k}]"
            parts.append(
                f"[{in_idx}:a]{atempo},"
                f"aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
                f"adelay={delay_ms}|{delay_ms}{label}"
            )
            audio_labels.append(label)

        has_audio = bool(audio_labels)
        if has_audio:
            if len(audio_labels) > 1:
                parts.append(
                    f"{''.join(audio_labels)}"
                    f"amix=inputs={len(audio_labels)}:normalize=0:dropout_transition=0[amix]"
                )
                mixed = "[amix]"
            else:
                mixed = audio_labels[0]
            # Pad with trailing silence so the audio always covers the full
            # video. apad is infinite, so the output length is bounded by the
            # explicit -t below (NOT -shortest, which hangs against apad).
            parts.append(f"{mixed}apad[aout]")

        if parts:
            cmd += ["-filter_complex", ";".join(parts)]
        cmd += ["-map", video_map]
        if has_audio:
            cmd += ["-map", "[aout]"]

        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
        if has_audio:
            cmd += ["-c:a", "aac"]
        # Bound the output to the video length so the infinitely-padded audio
        # track terminates deterministically.
        cmd += ["-t", f"{final_video_dur:.3f}", out_path]

        print(f"[StoryFinalCompile] scenes={n} videos={[os.path.basename(v) for v in videos]}")
        if has_audio:
            matched = [
                f"scene {scene_nums[i]}:{os.path.basename(p)}"
                for i, p, _ in audio_inputs
            ]
            print(f"[StoryFinalCompile] voiceovers ({len(audio_inputs)}/{n}): {matched}")
        else:
            print("[StoryFinalCompile] no voiceovers — compiling video only")
        print(f"[StoryFinalCompile] video_dur={final_video_dur:.2f}s -> {out_path}")

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
