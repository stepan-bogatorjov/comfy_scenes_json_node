"""StorySceneAutoQueue — ComfyUI node that chains scene execution automatically.

When enabled, after the current scene finishes it queues the next scene
by cloning the current prompt with an incremented scene_index.
ComfyUI processes queued prompts sequentially, so each scene completes
fully before the next one starts.

Scene count is derived automatically from the story JSON embedded in the
StorySceneSelector node — no manual configuration needed.

Requires scene_number wired from StorySceneSelector to guarantee
re-execution on every scene (prevents ComfyUI caching).
"""

import copy
import json
import threading
import urllib.error
import urllib.request

from ..utils.json_parser import load_story_json


def _get_comfyui_url():
    """Detect the ComfyUI server URL from the running instance."""
    try:
        import server
        port = server.PromptServer.instance.port
        return f"http://127.0.0.1:{port}"
    except Exception:
        return "http://127.0.0.1:8188"


def _queue_prompt_threaded(url, payload, label):
    """Queue a prompt via HTTP in a background thread.

    Using a thread avoids the Windows asyncio ConnectionResetError
    that occurs when making synchronous HTTP requests from within
    ComfyUI's async event loop.
    """
    def _do_request():
        try:
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req) as resp:
                resp.read()
            print(f"[StorySceneAutoQueue] {label}")
        except Exception as e:
            print(f"[StorySceneAutoQueue] Failed to queue: {e}")

    thread = threading.Thread(target=_do_request, daemon=True)
    thread.start()


class StorySceneAutoQueue:
    """Automatically queue the next scene after the current one completes."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "enabled": ("BOOLEAN", {"default": True}),
                "scene_number": ("INT", {"default": 1, "min": 1}),
            },
            "hidden": {
                "prompt": "PROMPT",
                "auth_token": "AUTH_TOKEN_COMFY_ORG",
                "api_key": "API_KEY_COMFY_ORG",
            },
        }

    RETURN_TYPES = ()
    OUTPUT_NODE = True
    FUNCTION = "auto_queue_next"
    CATEGORY = "ViralStory"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def auto_queue_next(self, enabled, scene_number, prompt, auth_token=None, api_key=None):
        if not enabled:
            print("[StorySceneAutoQueue] Disabled — running single scene only")
            return {}

        # Find the StorySceneSelector node in the current prompt
        selector_id = None
        current_index = 0
        json_text = ""
        file_path = ""
        for node_id, node in prompt.items():
            if isinstance(node, dict) and node.get("class_type") == "StorySceneSelector":
                selector_id = node_id
                inputs = node.get("inputs", {})
                current_index = inputs.get("scene_index", 0)
                json_text = inputs.get("json_text", "")
                file_path = inputs.get("file_path", "")
                break

        if selector_id is None:
            print("[StorySceneAutoQueue] No StorySceneSelector found in workflow")
            return {}

        # Get scene count from the story JSON
        try:
            story = load_story_json(json_text, file_path)
            scene_count = len(story["scenes"])
        except ValueError as e:
            print(f"[StorySceneAutoQueue] Cannot read story JSON: {e}")
            return {}

        next_index = current_index + 1
        scene_label = f"scene {scene_number}/{scene_count}"

        if next_index >= scene_count:
            print(f"[StorySceneAutoQueue] Finished last {scene_label}. All done!")
            return {}

        # Clone the prompt and set the next scene_index
        new_prompt = copy.deepcopy(prompt)
        new_prompt[selector_id]["inputs"]["scene_index"] = next_index

        # Forward auth credentials so API nodes work in queued prompts
        extra_data = {}
        if auth_token:
            extra_data["auth_token_comfy_org"] = auth_token
        if api_key:
            extra_data["api_key_comfy_org"] = api_key

        # Queue the next scene in a background thread to avoid
        # Windows asyncio ConnectionResetError
        base_url = _get_comfyui_url()
        payload = json.dumps({
            "prompt": new_prompt,
            "extra_data": extra_data,
        }).encode("utf-8")

        next_label = f"Done {scene_label} — queued next scene {next_index + 1}/{scene_count}"
        _queue_prompt_threaded(f"{base_url}/prompt", payload, next_label)

        return {}
