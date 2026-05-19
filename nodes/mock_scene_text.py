class MockSceneText:
    MODELS = [
        "gpt-5.5-pro",
        "gpt-5.5",
        "gpt-5-mini",
        "gpt-4.1",
        "gpt-4o",
        "mock",
    ]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "mock_response": ("STRING", {"multiline": True, "default": ""}),
                "persist_context": ("BOOLEAN", {"default": False}),
                "model": (cls.MODELS, {"default": "gpt-5.5-pro"}),
            },
            "optional": {
                "images": ("IMAGE",),
                "files": ("STRING", {"forceInput": True}),
                "advanced_options": ("DICT",),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("STRING",)
    FUNCTION = "generate"
    CATEGORY = "mock"

    def generate(self, prompt, mock_response, persist_context, model,
                 images=None, files=None, advanced_options=None):
        image_count = 0 if images is None else int(images.shape[0])
        file_count = 0 if not files else len([f for f in str(files).splitlines() if f.strip()])

        if mock_response:
            reply = mock_response
        else:
            reply = (
                f"[mock:{model}] prompt={prompt[:80]!r} "
                f"images={image_count} files={file_count} "
                f"persist_context={persist_context} "
                f"advanced_options={advanced_options!r}"
            )

        print(
            f"[MockSceneText] model={model} persist_context={persist_context} "
            f"images={image_count} files={file_count} "
            f"advanced_options={advanced_options!r} "
            f"prompt[:60]={prompt[:60]!r} "
            f"reply[:60]={reply[:60]!r}"
        )

        return (reply,)


NODE_CLASS_MAPPINGS = {
    "MockSceneText": MockSceneText,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MockSceneText": "Mock Scene Text",
}
