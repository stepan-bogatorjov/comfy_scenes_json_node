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


def _probe_video(ffmpeg_path: str, file_path: str) -> tuple[float, bool]:
    """Return (duration_seconds, has_audio_stream) for a video file."""
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
    duration = int(h) * 3600 + int(m) * 60 + float(s)
    has_audio = re.search(r"Stream #\d+:\d+.*: Audio:", result.stderr) is not None
    return duration, has_audio


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
                "original_audio_volume": ("FLOAT", {"default": 0.2, "min": 0.0, "max": 1.0, "step": 0.05}),
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
                transition_duration=0.2, original_audio_volume=0.2,
                filename_prefix="final"):
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
        v_probe = [_probe_video(ffmpeg, v) for v in videos]
        v_durations = [d for d, _ in v_probe]
        v_has_audio = [a for _, a in v_probe]

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

        # Match a voiceover to each scene by its number. Scenes without a file
        # stay silent (apart from their own quieter audio, mixed in below).
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

        # --- video filtergraph: crossfade chain ---
        video_parts = []
        if n > 1:
            prev = "[0:v]"
            cum = 0.0
            for i in range(1, n):
                cum += v_durations[i - 1]
                offset = cum - i * trans
                out_label = f"[v{i}]" if i < n - 1 else "[vout]"
                video_parts.append(
                    f"{prev}[{i}:v]xfade=transition=fade:"
                    f"duration={trans}:offset={offset:.3f}{out_label}"
                )
                prev = out_label
            video_map = "[vout]"
        else:
            video_map = "0:v"

        # --- audio filtergraph ---
        # Voiceovers sit on top; each scene's own audio is kept underneath at a
        # reduced volume. Everything is delayed to its scene's timeline start.
        # Input indices below assume: scene videos 0..n-1, voiceover files n..,
        # which is exactly the input order built for the audio pass.
        audio_parts = []
        audio_labels = []

        # Voiceover per scene: compressed only when LONGER than the scene so it
        # fits (atempo>1). A shorter voiceover is never slowed down — it plays
        # at natural speed from the scene start and the rest stays silent.
        for k, (i, _path, a_dur) in enumerate(audio_inputs):
            in_idx = n + k
            v_i = v_durations[i]
            tempo = max(1.0, a_dur / v_i) if v_i > 0 else 1.0
            atempo = _atempo_chain(tempo)
            delay_ms = int(round(starts[i] * 1000))
            label = f"[vo{k}]"
            audio_parts.append(
                f"[{in_idx}:a]{atempo},"
                f"aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
                f"adelay={delay_ms}|{delay_ms}{label}"
            )
            audio_labels.append(label)

        # Original scene audio at reduced volume, so background music/effects
        # survive under the voiceover instead of being dropped.
        if original_audio_volume > 0:
            for i in range(n):
                if not v_has_audio[i]:
                    continue
                delay_ms = int(round(starts[i] * 1000))
                label = f"[og{i}]"
                audio_parts.append(
                    f"[{i}:a]volume={original_audio_volume:.4f},"
                    f"aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
                    f"adelay={delay_ms}|{delay_ms}{label}"
                )
                audio_labels.append(label)

        has_audio = bool(audio_labels)
        if has_audio:
            if len(audio_labels) > 1:
                audio_parts.append(
                    f"{''.join(audio_labels)}"
                    f"amix=inputs={len(audio_labels)}:normalize=0:dropout_transition=0[amix]"
                )
                mixed = "[amix]"
            else:
                mixed = audio_labels[0]
            # Pad with trailing silence so the audio always covers the full
            # video. apad is infinite, so the output length is bounded by the
            # explicit -t below (NOT -shortest, which hangs against apad).
            audio_parts.append(f"{mixed}apad[aout]")

        dur = f"{final_video_dur:.3f}"

        print(f"[StoryFinalCompile] scenes={n} videos={[os.path.basename(v) for v in videos]}")
        if audio_inputs:
            matched = [
                f"scene {scene_nums[i]}:{os.path.basename(p)}"
                for i, p, _ in audio_inputs
            ]
            print(f"[StoryFinalCompile] voiceovers ({len(audio_inputs)}/{n}): {matched}")
        else:
            print("[StoryFinalCompile] no voiceovers")
        n_og = sum(v_has_audio) if original_audio_volume > 0 else 0
        print(f"[StoryFinalCompile] original audio: {n_og}/{n} scenes @ vol {original_audio_volume}")
        print(f"[StoryFinalCompile] video_dur={final_video_dur:.2f}s -> {out_path}")

        def _run(cmd_args):
            result = subprocess.run(
                cmd_args, capture_output=True, text=True,
                encoding="utf-8", errors="replace",
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"[StoryFinalCompile] ffmpeg failed (exit {result.returncode}):\n"
                    f"{result.stderr[-2000:]}"
                )

        # No audio at all -> a single video pass (nothing competes with xfade).
        if not has_audio:
            cmd = [ffmpeg, "-y", "-nostdin"]
            for v in videos:
                cmd += ["-i", v]
            if video_parts:
                cmd += ["-filter_complex", ";".join(video_parts)]
            cmd += ["-map", video_map, "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-t", dur, out_path]
            _run(cmd)
            return (out_path,)

        # Two passes. Feeding each scene's mp4 into BOTH the xfade video chain
        # and the audio amix in one command deadlocks ffmpeg: xfade buffers
        # video while amix pulls audio from the same inputs, and the input
        # queue stalls. So render the video first, then mux the audio against
        # the finished video — in the audio pass the mp4s contribute audio
        # only, so nothing competes with a video filter.
        tmp_video = os.path.join(output_dir, f".{out_name}.video.tmp.mp4")
        try:
            # Pass 1: crossfaded video, no audio.
            cmd1 = [ffmpeg, "-y", "-nostdin"]
            for v in videos:
                cmd1 += ["-i", v]
            if video_parts:
                cmd1 += ["-filter_complex", ";".join(video_parts)]
            cmd1 += ["-map", video_map, "-an", "-c:v", "libx264",
                     "-pix_fmt", "yuv420p", "-t", dur, tmp_video]
            _run(cmd1)

            # Pass 2: audio mix over the finished video. Input order matches the
            # indices used in the audio filtergraph: scene videos 0..n-1 (their
            # audio only), voiceovers n.., and the finished video last.
            cmd2 = [ffmpeg, "-y", "-nostdin"]
            for v in videos:
                cmd2 += ["-i", v]
            for _, path, _ in audio_inputs:
                cmd2 += ["-i", path]
            cmd2 += ["-i", tmp_video]
            vid_idx = n + len(audio_inputs)
            cmd2 += ["-filter_complex", ";".join(audio_parts),
                     "-map", f"{vid_idx}:v", "-map", "[aout]",
                     "-c:v", "copy", "-c:a", "aac", "-t", dur, out_path]
            _run(cmd2)
        finally:
            if os.path.exists(tmp_video):
                try:
                    os.remove(tmp_video)
                except OSError:
                    pass

        return (out_path,)


NODE_CLASS_MAPPINGS = {
    "StoryFinalCompile": StoryFinalCompile,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "StoryFinalCompile": "Story Final Compile",
}
