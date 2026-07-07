import json
import os
import re
import shutil
import subprocess

import folder_paths

# Fonts for burned-in subtitles: italic for the (off-screen) voiceover
# narration, regular for in-video character dialogue.
SUBTITLE_FONT_ITALIC = r"C:\Windows\Fonts\ariali.ttf"
SUBTITLE_FONT_REGULAR = r"C:\Windows\Fonts\arial.ttf"
SUBTITLE_MAX_LINES = 3  # wrap long text onto up to this many lines


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
# Story JSON saved by SaveTextPassthrough (prefix "scene"): "scene_00001.txt".
STORY_JSON_RE = re.compile(r"^scene_(\d+)\.txt$", re.IGNORECASE)


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


def _probe_size(ffmpeg_path: str, file_path: str) -> tuple[int, int]:
    """Return (width, height) of a video's first real video stream, or
    (None, None) if it can't be parsed. Skips 'attached pic' cover streams."""
    result = subprocess.run(
        [ffmpeg_path, "-i", file_path, "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    for line in result.stderr.splitlines():
        if ": Video:" in line and "attached pic" not in line:
            m = re.search(r",\s*(\d{2,5})x(\d{2,5})", line)
            if m:
                return int(m.group(1)), int(m.group(2))
    return None, None


def _ff_escape_path(path: str) -> str:
    """Escape a filesystem path for use as a value inside an ffmpeg filter
    (forward slashes, and the Windows drive colon escaped)."""
    return path.replace("\\", "/").replace(":", r"\:")


def _greedy_wrap(words, font, max_width, force=False):
    """Greedy word-wrap `words` so each line fits max_width px in `font`.
    Returns list of lines, or None if a single word is too wide (caller should
    try a smaller font). With force=True, oversized words are kept anyway."""
    lines, cur = [], ""
    for word in words:
        trial = f"{cur} {word}" if cur else word
        if font.getlength(trial) <= max_width:
            cur = trial
            continue
        if cur:
            lines.append(cur)
        if not force and font.getlength(word) > max_width:
            return None
        cur = word
    if cur:
        lines.append(cur)
    return lines


def _wrap_to_fit(text, font_path, max_width, max_size, min_size, max_lines):
    """Return (font_size, [lines]): the largest size in [min_size, max_size]
    whose word-wrap fits max_width in <= max_lines lines. Falls back to
    min_size (wrapping anyway) if nothing fits, or a single line if PIL is
    unavailable."""
    try:
        from PIL import ImageFont
    except ImportError:
        return int(min_size), [text]
    words = text.split()
    for size in range(int(max_size), int(min_size) - 1, -1):
        try:
            font = ImageFont.truetype(font_path, size)
        except OSError:
            return int(max_size), [text]
        lines = _greedy_wrap(words, font, max_width)
        if lines is not None and len(lines) <= max_lines:
            return size, lines
    font = ImageFont.truetype(font_path, int(min_size))
    return int(min_size), _greedy_wrap(words, font, max_width, force=True)


def _load_subtitle_sources(json_path: str):
    """Parse a story JSON into two maps:
      voiceover: scene_num -> narration line   (scenes[].voiceover.text)
      dialogue:  scene_num -> [dialogue lines]  (scenes[].subtitles[].text)
    Each string is collapsed to a single line. Empty maps on any problem."""
    voiceover: dict[int, str] = {}
    dialogue: dict[int, list] = {}
    if not json_path or not os.path.isfile(json_path):
        return voiceover, dialogue
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return voiceover, dialogue
    for scene in data.get("scenes", []) if isinstance(data, dict) else []:
        if not isinstance(scene, dict):
            continue
        num = scene.get("scene")
        if not isinstance(num, int):
            continue
        vo = scene.get("voiceover")
        if isinstance(vo, dict) and vo.get("text"):
            voiceover[num] = " ".join(str(vo["text"]).split())
        subs = scene.get("subtitles")
        if isinstance(subs, list):
            lines = [" ".join(str(s["text"]).split()) for s in subs
                     if isinstance(s, dict) and s.get("text")]
            if lines:
                dialogue[num] = lines
    return voiceover, dialogue


def _find_story_json(output_dir: str) -> str:
    """Newest 'scene_<counter>.txt' in output_dir — the story JSON saved during
    a run (it lives here until CollectRunOutputs archives it). '' if none."""
    best = None  # (counter, path)
    try:
        entries = os.listdir(output_dir)
    except OSError:
        return ""
    for name in entries:
        match = STORY_JSON_RE.match(name)
        if match:
            counter = int(match.group(1))
            if best is None or counter > best[0]:
                best = (counter, os.path.join(output_dir, name))
    return best[1] if best else ""


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
                "voiceover_volume": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.05}),
                "original_audio_volume": ("FLOAT", {"default": 0.2, "min": 0.0, "max": 1.0, "step": 0.05}),
                "voiceover_subtitles": ("BOOLEAN", {"default": False}),
                "dialogue_subtitles": ("BOOLEAN", {"default": False}),
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
                transition_duration=0.2, voiceover_volume=1.0,
                original_audio_volume=0.2, voiceover_subtitles=False,
                dialogue_subtitles=False, filename_prefix="final"):
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

        # --- subtitles (both OFF by default) ---
        # voiceover_subtitles -> scenes[].voiceover.text : italic off-screen
        #   narration, spans the whole scene.
        # dialogue_subtitles  -> scenes[].subtitles[].text : regular in-video
        #   speech. One entry fills the scene; several split the scene by text
        #   length and show one at a time (drawtext enable window).
        # Story JSON is auto-located in the output dir (it lives there until
        # CollectRunOutputs archives it).
        vo_texts, dlg_lists = {}, {}
        if voiceover_subtitles or dialogue_subtitles:
            vo_texts, dlg_lists = _load_subtitle_sources(_find_story_json(output_dir))

        sub_tmp_files = []
        scene_drawtext = {}  # video index -> filterchain of stacked drawtext
        for i in range(n):
            num, scene_dur = scene_nums[i], v_durations[i]
            # (text, font, window) items for this scene; window=None spans all.
            items = []
            if voiceover_subtitles and num in vo_texts:
                items.append((vo_texts[num], SUBTITLE_FONT_ITALIC, None))
            if dialogue_subtitles and num in dlg_lists:
                lines_ = dlg_lists[num]
                if len(lines_) == 1:
                    items.append((lines_[0], SUBTITLE_FONT_REGULAR, None))
                else:
                    weights = [max(1, len(t)) for t in lines_]
                    total = sum(weights)
                    acc = 0.0
                    for text, wgt in zip(lines_, weights):
                        start = scene_dur * acc / total
                        acc += wgt
                        items.append((text, SUBTITLE_FONT_REGULAR,
                                      (start, scene_dur * acc / total)))
            if not items:
                continue

            w, h = _probe_size(ffmpeg, videos[i])
            w, h = w or 480, h or 848
            max_w = w - 2 * max(8, int(w * 0.05))
            max_size = max(20, int(h * 0.042))
            bottom = max(12, int(h * 0.06))

            draws = []
            for j, (text, font_path, window) in enumerate(items):
                fs, lines = _wrap_to_fit(text, font_path, max_w,
                                         max_size=max_size, min_size=16,
                                         max_lines=SUBTITLE_MAX_LINES)
                border = max(2, fs // 10)
                line_h = int(round(fs * 1.3))
                top = h - bottom - len(lines) * line_h
                # A timed item is only shown during its clip-local window;
                # commas inside between() are protected by the single quotes.
                enable = ("" if window is None else
                          f":enable='between(t,{window[0]:.3f},{window[1]:.3f})'")
                for k, line in enumerate(lines):
                    # ffmpeg runs with cwd=output_dir (see _run), so reference
                    # the subtitle file by basename — no spaces/colon to escape.
                    sub_name = f".{out_name}.sub{i}_{j}_{k}.txt"
                    with open(os.path.join(output_dir, sub_name), "w", encoding="utf-8") as f:
                        f.write(line)
                    sub_tmp_files.append(os.path.join(output_dir, sub_name))
                    draws.append(
                        f"drawtext=fontfile='{_ff_escape_path(font_path)}':"
                        f"textfile={sub_name}:"
                        f"fontsize={fs}:fontcolor=white:borderw={border}:bordercolor=black:"
                        f"x=(w-text_w)/2:y={top + k * line_h}{enable}"
                    )
            scene_drawtext[i] = ",".join(draws)

        # --- video filtergraph: per-scene subtitle overlay, then crossfade ---
        video_parts = []
        scene_src = []  # xfade input label for each scene (subtitled or raw)
        for i in range(n):
            dt = scene_drawtext.get(i)
            if dt:
                label = f"[sv{i}]"
                video_parts.append(f"[{i}:v]{dt}{label}")
                scene_src.append(label)
            else:
                scene_src.append(f"[{i}:v]")

        if n > 1:
            prev = scene_src[0]
            cum = 0.0
            for i in range(1, n):
                cum += v_durations[i - 1]
                offset = cum - i * trans
                out_label = f"[v{i}]" if i < n - 1 else "[vout]"
                video_parts.append(
                    f"{prev}{scene_src[i]}xfade=transition=fade:"
                    f"duration={trans}:offset={offset:.3f}{out_label}"
                )
                prev = out_label
            video_map = "[vout]"
        else:
            # Single scene: map its subtitled output if any, else the raw stream.
            video_map = scene_src[0] if 0 in scene_drawtext else "0:v"

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
                f"[{in_idx}:a]{atempo},volume={voiceover_volume:.4f},"
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
            print(f"[StoryFinalCompile] voiceovers ({len(audio_inputs)}/{n}) @ vol {voiceover_volume}: {matched}")
        else:
            print("[StoryFinalCompile] no voiceovers")
        n_og = sum(v_has_audio) if original_audio_volume > 0 else 0
        print(f"[StoryFinalCompile] original audio: {n_og}/{n} scenes @ vol {original_audio_volume}")
        if scene_drawtext:
            subbed = [scene_nums[i] for i in sorted(scene_drawtext)]
            print(f"[StoryFinalCompile] subtitles (voiceover={voiceover_subtitles} "
                  f"dialogue={dialogue_subtitles}) on scenes {subbed}")
        print(f"[StoryFinalCompile] video_dur={final_video_dur:.2f}s -> {out_path}")

        def _run(cmd_args):
            # cwd=output_dir so drawtext can reference subtitle files by
            # basename (avoids escaping spaces/colons in the filtergraph).
            result = subprocess.run(
                cmd_args, capture_output=True, text=True,
                encoding="utf-8", errors="replace", cwd=output_dir,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"[StoryFinalCompile] ffmpeg failed (exit {result.returncode}):\n"
                    f"{result.stderr[-2000:]}"
                )

        tmp_video = None
        try:
            # No audio -> a single video pass (nothing competes with xfade).
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

            # Two passes. Feeding each scene's mp4 into BOTH the xfade video
            # chain and the audio amix in one command deadlocks ffmpeg: xfade
            # buffers video while amix pulls audio from the same inputs, and the
            # input queue stalls. So render the video first, then mux the audio
            # against the finished video — in the audio pass the mp4s contribute
            # audio only, so nothing competes with a video filter.
            tmp_video = os.path.join(output_dir, f".{out_name}.video.tmp.mp4")

            # Pass 1: crossfaded (and subtitled) video, no audio.
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
            return (out_path,)
        finally:
            leftovers = list(sub_tmp_files)
            if tmp_video:
                leftovers.append(tmp_video)
            for path in leftovers:
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass


NODE_CLASS_MAPPINGS = {
    "StoryFinalCompile": StoryFinalCompile,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "StoryFinalCompile": "Story Final Compile",
}
