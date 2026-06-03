import os
import re
import shutil
from datetime import datetime

import folder_paths


class _AnyType(str):
    def __ne__(self, other):
        return False

    def __eq__(self, other):
        return True

    def __hash__(self):
        return id(self)


ANY = _AnyType("*")


_STRFTIME_TO_RE = {
    "%d": r"\d{2}", "%m": r"\d{2}", "%Y": r"\d{4}", "%y": r"\d{2}",
    "%H": r"\d{2}", "%M": r"\d{2}", "%S": r"\d{2}", "%j": r"\d{3}",
}


def _archive_pattern(date_format: str) -> re.Pattern:
    """Regex matching this node's own run-archive folders ("<date> NNN") for
    ANY date, derived from date_format — so we never re-archive past runs."""
    fmt = date_format or "%d.%m.%Y"
    out = []
    i = 0
    while i < len(fmt):
        token = fmt[i:i + 2]
        if token in _STRFTIME_TO_RE:
            out.append(_STRFTIME_TO_RE[token])
            i += 2
        else:
            out.append(re.escape(fmt[i]))
            i += 1
    return re.compile(rf"^{''.join(out)}\s+\d+$")


def _next_folder_index(output_dir: str, date_str: str) -> int:
    """Find the next free NNN for a given date prefix in output_dir."""
    # Matches "<date> 001", "<date> 042" etc. (3-digit zero-padded by default,
    # but we tolerate any positive number of digits so manual folders fit too).
    pattern = re.compile(rf"^{re.escape(date_str)}\s+(\d+)$")
    max_seen = 0
    try:
        entries = os.listdir(output_dir)
    except FileNotFoundError:
        return 1
    for name in entries:
        full = os.path.join(output_dir, name)
        if not os.path.isdir(full):
            continue
        match = pattern.match(name)
        if match:
            max_seen = max(max_seen, int(match.group(1)))
    return max_seen + 1


class CollectRunOutputs:
    """Move every loose item from output/ into output/<DD.MM.YYYY NNN>/.

    Both loose files (e.g. final_00001.mp4) and subfolders (e.g. scenes/,
    voiceover/) produced during a run are archived; previously-created run
    folders ("<date> NNN") are skipped so past runs are never re-moved.

    Designed to run after StoryFinalCompile — wire its `output_path` into the
    `trigger` socket. Date is the local date at run time; NNN auto-increments
    from existing folders for that date.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "trigger": (ANY, {}),
            },
            "optional": {
                "date_format": ("STRING", {"default": "%d.%m.%Y"}),
                "index_padding": ("INT", {"default": 3, "min": 1, "max": 6, "step": 1}),
                "dry_run": ("BOOLEAN", {"default": False}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("folder_path",)
    FUNCTION = "collect"
    CATEGORY = "video"
    OUTPUT_NODE = True

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def collect(self, trigger, date_format: str = "%d.%m.%Y",
                index_padding: int = 3, dry_run: bool = False):
        output_dir = folder_paths.get_output_directory()
        os.makedirs(output_dir, exist_ok=True)

        date_str = datetime.now().strftime(date_format or "%d.%m.%Y")
        next_idx = _next_folder_index(output_dir, date_str)
        folder_name = f"{date_str} {next_idx:0{index_padding}d}"
        target_dir = os.path.join(output_dir, folder_name)

        # Snapshot loose items first. Skip our own run-archive folders ("<date>
        # NNN") so previous runs (and the target dir itself) are never re-moved;
        # everything else — loose files and content subfolders — gets archived.
        archive_re = _archive_pattern(date_format)
        loose_items = [
            name for name in os.listdir(output_dir)
            if not (os.path.isdir(os.path.join(output_dir, name)) and archive_re.match(name))
        ]

        if not loose_items:
            print(f"[CollectRunOutputs] no loose items in {output_dir} — nothing to move")
            return (output_dir,)

        if dry_run:
            print(f"[CollectRunOutputs] DRY RUN -> would create {target_dir}")
            for name in loose_items:
                print(f"[CollectRunOutputs] DRY RUN -> would move {name}")
            return (target_dir,)

        os.makedirs(target_dir, exist_ok=True)

        moved = 0
        for name in loose_items:
            src = os.path.join(output_dir, name)
            dst = os.path.join(target_dir, name)
            # Defensive — if a file with the same name already exists in
            # target (shouldn't happen on a fresh NNN), suffix it instead of
            # overwriting work.
            if os.path.exists(dst):
                stem, ext = os.path.splitext(name)
                i = 1
                while True:
                    alt = os.path.join(target_dir, f"{stem}__{i}{ext}")
                    if not os.path.exists(alt):
                        dst = alt
                        break
                    i += 1
            shutil.move(src, dst)
            moved += 1

        print(f"[CollectRunOutputs] moved {moved} item(s) -> {target_dir}")
        return (target_dir,)


NODE_CLASS_MAPPINGS = {
    "CollectRunOutputs": CollectRunOutputs,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "CollectRunOutputs": "Collect Run Outputs",
}
