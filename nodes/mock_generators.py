from fractions import Fraction

import torch


class MockSceneImage:
    QUALITIES = ["low", "medium", "high", "auto"]
    BACKGROUNDS = ["auto", "transparent", "opaque"]
    SIZES = ["auto", "1024x1024", "1024x1536", "1536x1024"]
    MODELS = ["gpt-image-1.5", "gpt-image-1", "mock"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF}),
                "quality": (cls.QUALITIES, {"default": "low"}),
                "background": (cls.BACKGROUNDS, {"default": "auto"}),
                "size": (cls.SIZES, {"default": "auto"}),
                "n": ("INT", {"default": 1, "min": 1, "max": 8}),
                "model": (cls.MODELS, {"default": "gpt-image-1.5"}),
            },
            "optional": {
                "image": ("IMAGE",),
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("IMAGE",)
    FUNCTION = "generate"
    CATEGORY = "mock"

    @staticmethod
    def _resolve_size(size):
        if size == "auto" or "x" not in size:
            return 768, 1344
        w, h = size.lower().split("x")
        return int(w), int(h)

    def generate(self, prompt, seed, quality, background, size, n, model,
                 image=None, mask=None):
        w, h = self._resolve_size(size)
        generator = torch.Generator().manual_seed(int(seed) & 0xFFFFFFFF)

        hue = (torch.rand(3, generator=generator) * 0.7 + 0.2).tolist()
        ys = torch.linspace(0.25, 1.0, h).view(1, h, 1)
        xs = torch.linspace(0.25, 1.0, w).view(1, 1, w)
        gradient = (ys * xs).unsqueeze(-1)

        batch = gradient.repeat(n, 1, 1, 3)
        for c in range(3):
            batch[..., c] *= hue[c]

        noise = torch.randn(batch.shape, generator=generator) * 0.03
        batch = torch.clamp(batch + noise, 0.0, 1.0)

        print(
            f"[MockSceneImage] seed={seed} size={w}x{h} n={n} "
            f"quality={quality} bg={background} model={model} "
            f"prompt[:60]={prompt[:60]!r}"
        )
        return (batch,)


class MockSceneVideo:
    MODELS = ["grok-imagine-video", "mock"]
    RESOLUTIONS = ["480p", "720p", "1080p"]
    ASPECTS = ["9:16", "16:9", "1:1"]
    FPS = 24

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "model": (cls.MODELS, {"default": "grok-imagine-video"}),
                "resolution": (cls.RESOLUTIONS, {"default": "480p"}),
                "aspect_ratio": (cls.ASPECTS, {"default": "9:16"}),
                "duration": ("INT", {"default": 5, "min": 1, "max": 60}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF}),
            },
            "optional": {
                "reference_0": ("IMAGE",),
                "reference_1": ("IMAGE",),
            },
        }

    RETURN_TYPES = ("VIDEO",)
    RETURN_NAMES = ("VIDEO",)
    FUNCTION = "generate"
    CATEGORY = "mock"

    @staticmethod
    def _resolve_dims(resolution, aspect_ratio):
        short_side = {"480p": 480, "720p": 720, "1080p": 1080}.get(resolution, 480)
        aw, ah = (int(x) for x in aspect_ratio.split(":"))
        if aw >= ah:
            h = short_side
            w = int(round(h * aw / ah))
        else:
            w = short_side
            h = int(round(w * ah / aw))
        return w - (w % 2), h - (h % 2)

    @staticmethod
    def _resize(frame, h, w):
        return torch.nn.functional.interpolate(
            frame.permute(2, 0, 1).unsqueeze(0),
            size=(h, w), mode="bilinear", align_corners=False,
        ).squeeze(0).permute(1, 2, 0).clamp(0.0, 1.0)

    def generate(self, prompt, model, resolution, aspect_ratio, duration, seed,
                 reference_0=None, reference_1=None):
        from comfy_api.input_impl import VideoFromComponents
        from comfy_api.util import VideoComponents

        w, h = self._resolve_dims(resolution, aspect_ratio)
        frame_count = max(1, int(duration) * self.FPS)

        if reference_0 is not None:
            base = self._resize(reference_0[0], h, w)
        elif reference_1 is not None:
            base = self._resize(reference_1[0], h, w)
        else:
            base = torch.full((h, w, 3), 0.5, dtype=torch.float32)

        t = torch.linspace(-0.08, 0.08, frame_count).view(frame_count, 1, 1, 1)
        frames = torch.clamp(base.unsqueeze(0) + t, 0.0, 1.0)

        print(
            f"[MockSceneVideo] seed={seed} {w}x{h}@{self.FPS}fps "
            f"duration={duration}s frames={frame_count} model={model} "
            f"prompt[:60]={prompt[:60]!r}"
        )

        video = VideoFromComponents(VideoComponents(
            images=frames,
            audio=None,
            frame_rate=Fraction(self.FPS),
        ))
        return (video,)


NODE_CLASS_MAPPINGS = {
    "MockSceneImage": MockSceneImage,
    "MockSceneVideo": MockSceneVideo,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MockSceneImage": "Mock Scene Image",
    "MockSceneVideo": "Mock Scene Video",
}
