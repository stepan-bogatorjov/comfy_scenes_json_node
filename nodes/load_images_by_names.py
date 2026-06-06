import ast
import json
import os

import numpy as np
import torch
from PIL import Image, ImageOps

import folder_paths


class _AnyType(str):
    def __ne__(self, other):
        return False

    def __eq__(self, other):
        return True

    def __hash__(self):
        return id(self)


ANY = _AnyType("*")

VALID_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".tga", ".bmp")


def _coerce_names(names) -> list[str]:
    """Accept a real list/tuple, a JSON array string, a Python-repr list
    string (single quotes), or a comma/newline separated string and return a
    clean list of names."""
    if names is None:
        return []
    if isinstance(names, (list, tuple)):
        items = names
    elif isinstance(names, str):
        text = names.strip()
        if not text:
            return []
        items = None
        # Try strict JSON first, then a Python literal (handles single quotes).
        for parse in (json.loads, ast.literal_eval):
            try:
                parsed = parse(text)
            except (ValueError, SyntaxError, TypeError):
                continue
            items = list(parsed) if isinstance(parsed, (list, tuple)) else [parsed]
            break
        if items is None:
            items = text.replace(",", "\n").splitlines()
    else:
        items = [names]
    # Strip whitespace plus any stray brackets/quotes left by a fallback split.
    cleaned = [str(x).strip().strip("[]'\" ") for x in items]
    return [x for x in cleaned if x]


class LoadImagesByNames:
    """Load images from a folder whose filenames match a list of names.

    Input `names` may be a list of strings (e.g. ["milo", "luna"]), a JSON
    array string, or a comma/newline separated string. For each name the
    folder is searched for a file with that stem and any image extension, in
    input order. If the resulting list is empty (no names, or none found), a
    single 1x1 placeholder image is returned instead.

    Output types match the other loaders (IMAGE, MASK, INT, STRING).
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "names": (ANY, {"forceInput": True}),
                "folder": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "INT", "STRING")
    RETURN_NAMES = ("image", "mask", "count", "image_path")
    FUNCTION = "load"
    CATEGORY = "image"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def _resolve_folder(self, folder: str) -> str:
        folder = (folder or "").strip()
        if folder and not os.path.isabs(folder):
            folder = os.path.join(folder_paths.get_output_directory(), folder)
        return folder

    def _build_index(self, folder: str) -> dict[str, str]:
        """Map lowercased filename-stem -> full path (first match wins)."""
        index: dict[str, str] = {}
        if not folder or not os.path.isdir(folder):
            return index
        for name in sorted(os.listdir(folder)):
            full = os.path.join(folder, name)
            if not os.path.isfile(full):
                continue
            stem, ext = os.path.splitext(name)
            if ext.lower() in VALID_EXTENSIONS:
                index.setdefault(stem.lower(), full)
        return index

    @staticmethod
    def _placeholder():
        image = torch.zeros((1, 1, 1, 3), dtype=torch.float32)
        mask = torch.zeros((1, 1, 1), dtype=torch.float32)
        return (image, mask, 0, [])

    def load(self, names, folder):
        wanted = _coerce_names(names)
        if not wanted:
            print("[LoadImagesByNames] empty names list — returning 1x1 placeholder")
            return self._placeholder()

        folder = self._resolve_folder(folder)
        index = self._build_index(folder)

        paths = []
        for name in wanted:
            match = index.get(name.lower())
            if match:
                paths.append(match)
            else:
                print(f"[LoadImagesByNames] no file for '{name}' in {folder} — skipped")

        if not paths:
            print("[LoadImagesByNames] nothing matched — returning 1x1 placeholder")
            return self._placeholder()

        images = []
        masks = []
        target_size = None  # (width, height) from the first loaded image
        for path in paths:
            img = ImageOps.exif_transpose(Image.open(path))

            if target_size is None:
                target_size = img.size
            elif img.size != target_size:
                img = img.resize(target_size, Image.Resampling.LANCZOS)

            width, height = target_size

            rgb = np.array(img.convert("RGB")).astype(np.float32) / 255.0
            images.append(torch.from_numpy(rgb)[None,])

            if "A" in img.getbands():
                alpha = np.array(img.getchannel("A")).astype(np.float32) / 255.0
                masks.append(1.0 - torch.from_numpy(alpha))
            else:
                masks.append(torch.zeros((height, width), dtype=torch.float32))

        image_batch = torch.cat(images, dim=0)
        mask_batch = torch.stack(masks, dim=0)

        print(f"[LoadImagesByNames] loaded {len(paths)}/{len(wanted)} image(s) from {folder}")

        return (image_batch, mask_batch, len(paths), paths)


NODE_CLASS_MAPPINGS = {
    "LoadImagesByNames": LoadImagesByNames,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LoadImagesByNames": "Load Images By Names",
}
