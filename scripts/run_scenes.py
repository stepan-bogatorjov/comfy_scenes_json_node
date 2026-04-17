"""Queue all (or one) scene(s) from a story-driven ComfyUI workflow.

Reads the API-format workflow JSON, finds the StorySceneSelector node,
determines scene count from the embedded story JSON, then submits each
scene to the ComfyUI queue — waiting for completion between scenes.

Usage:
    python run_scenes.py --workflow input/scene_generation_validate.json
    python run_scenes.py --workflow input/scene_generation_validate.json --scene 3
    python run_scenes.py --workflow input/scene_generation_validate.json --host 192.168.1.10:8188
"""

import argparse
import copy
import json
import sys
import time
import urllib.error
import urllib.request


def find_node_by_class(workflow: dict, class_type: str) -> tuple[str, dict]:
    """Find a node in the workflow by its class_type. Returns (node_id, node_dict)."""
    for node_id, node in workflow.items():
        if node.get("class_type") == class_type:
            return node_id, node
    raise ValueError(f"No node with class_type '{class_type}' found in workflow")


def get_scene_count(workflow: dict) -> int:
    """Extract scene count from the story JSON embedded in the workflow."""
    # Try StorySceneSelector first, then StoryJsonLoader
    for class_type in ("StorySceneSelector", "StoryJsonLoader"):
        try:
            _, node = find_node_by_class(workflow, class_type)
        except ValueError:
            continue

        inputs = node.get("inputs", {})
        json_text = inputs.get("json_text", "").strip()
        file_path = inputs.get("file_path", "").strip()

        if json_text:
            story = json.loads(json_text)
            return len(story["scenes"])

        if file_path:
            with open(file_path, "r", encoding="utf-8") as f:
                story = json.load(f)
            return len(story["scenes"])

    raise ValueError("Cannot determine scene count: no story JSON found in workflow nodes")


def queue_prompt(workflow: dict, host: str) -> str:
    """Submit a workflow to ComfyUI and return the prompt_id."""
    payload = json.dumps({"prompt": workflow}).encode("utf-8")
    req = urllib.request.Request(
        f"http://{host}/prompt",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())
    return result["prompt_id"]


def wait_for_completion(prompt_id: str, host: str, poll_interval: float = 2.0):
    """Poll ComfyUI /history until the prompt finishes or errors."""
    url = f"http://{host}/history/{prompt_id}"
    while True:
        try:
            with urllib.request.urlopen(url) as resp:
                history = json.loads(resp.read())
        except urllib.error.URLError:
            time.sleep(poll_interval)
            continue

        if prompt_id not in history:
            # Not started yet
            time.sleep(poll_interval)
            continue

        entry = history[prompt_id]
        status = entry.get("status", {})

        if status.get("completed", False):
            return True

        if status.get("status_str") == "error":
            messages = entry.get("status", {}).get("messages", [])
            print(f"  ERROR: {messages}", file=sys.stderr)
            return False

        time.sleep(poll_interval)


def run(workflow_path: str, scene_index: int | None, host: str):
    """Main execution: load workflow, determine scenes, queue them."""
    with open(workflow_path, "r", encoding="utf-8") as f:
        workflow = json.load(f)

    selector_id, _ = find_node_by_class(workflow, "StorySceneSelector")
    scene_count = get_scene_count(workflow)

    if scene_index is not None:
        if scene_index < 0 or scene_index >= scene_count:
            print(f"Error: scene {scene_index} out of range (0-{scene_count - 1})", file=sys.stderr)
            sys.exit(1)
        scenes_to_run = [scene_index]
    else:
        scenes_to_run = list(range(scene_count))

    print(f"Workflow: {workflow_path}")
    print(f"Scenes:   {len(scenes_to_run)} of {scene_count} total")
    print(f"ComfyUI:  http://{host}")
    print()

    for i, idx in enumerate(scenes_to_run):
        prompt = copy.deepcopy(workflow)
        prompt[selector_id]["inputs"]["scene_index"] = idx

        scene_num = idx + 1
        print(f"[{i + 1}/{len(scenes_to_run)}] Queuing scene {scene_num} (index {idx})...", end=" ", flush=True)

        try:
            prompt_id = queue_prompt(prompt, host)
        except urllib.error.URLError as e:
            print(f"\nError: Cannot connect to ComfyUI at http://{host} — {e}", file=sys.stderr)
            print("Make sure ComfyUI is running.", file=sys.stderr)
            sys.exit(1)

        print(f"queued (id: {prompt_id[:8]}...)")
        print(f"         Waiting for completion...", end=" ", flush=True)

        success = wait_for_completion(prompt_id, host)
        if success:
            print("done")
        else:
            print("FAILED")
            print(f"  Scene {scene_num} failed. Stopping.", file=sys.stderr)
            sys.exit(1)

    print()
    print(f"All {len(scenes_to_run)} scene(s) completed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Queue story scenes to ComfyUI")
    parser.add_argument(
        "--workflow", required=True,
        help="Path to the API-format workflow JSON"
    )
    parser.add_argument(
        "--scene", type=int, default=None,
        help="Run a specific scene index (0-based). Omit to run all scenes."
    )
    parser.add_argument(
        "--host", default="127.0.0.1:8188",
        help="ComfyUI server address (default: 127.0.0.1:8188)"
    )
    args = parser.parse_args()
    run(args.workflow, args.scene, args.host)
