from __future__ import annotations

import base64
import io
import json
import time
import uuid
from pathlib import Path

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

COMFY_API = "http://127.0.0.1:8188"
ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "tools" / "ComfyUI" / "output"
CHECKPOINT_NAME = "v1-5-pruned-emaonly.safetensors"


def _workflow(prompt_text: str) -> dict:
    return {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": int(time.time()) % 4294967295,
                "steps": 8,
                "cfg": 7.0,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": CHECKPOINT_NAME,
            },
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": 512,
                "height": 512,
                "batch_size": 1,
            },
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": prompt_text,
                "clip": ["4", 1],
            },
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "low quality, blurry, deformed, text",
                "clip": ["4", 1],
            },
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["3", 0],
                "vae": ["4", 2],
            },
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": "phase1_bridge",
                "images": ["8", 0],
            },
        },
    }


def _submit_prompt(prompt_text: str) -> str:
    payload = {"prompt": _workflow(prompt_text), "client_id": str(uuid.uuid4())}
    response = requests.post(f"{COMFY_API}/prompt", json=payload, timeout=30)
    response.raise_for_status()
    return response.json()["prompt_id"]


def _wait_for_result(prompt_id: str, timeout_seconds: int = 3600) -> Path:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        history_resp = requests.get(f"{COMFY_API}/history/{prompt_id}", timeout=20)
        history_resp.raise_for_status()
        history = history_resp.json()
        if prompt_id in history:
            node_outputs = history[prompt_id].get("outputs", {})
            for node in node_outputs.values():
                for image_info in node.get("images", []):
                    filename = image_info.get("filename")
                    subfolder = image_info.get("subfolder", "")
                    image_path = OUTPUT_DIR / subfolder / filename
                    if image_path.exists():
                        return image_path
        time.sleep(1.2)
    raise TimeoutError("Timed out waiting for ComfyUI image output")


@app.route("/generate", methods=["POST"])
def generate():
    payload = request.get_json(force=True)
    prompt_text = payload.get("prompt", "character portrait")
    output_path = payload.get("output_path")
    if not output_path:
        return jsonify({"error": "output_path is required"}), 400

    try:
        prompt_id = _submit_prompt(prompt_text)
        generated_path = _wait_for_result(prompt_id)
        image_bytes = generated_path.read_bytes()
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(image_bytes)
        return jsonify({"image_base64": base64.b64encode(image_bytes).decode("utf-8")})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


@app.route("/health", methods=["GET"])
def health():
    try:
        requests.get(f"{COMFY_API}/system_stats", timeout=10).raise_for_status()
        return jsonify({"status": "ok"})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"status": "down", "detail": str(exc)}), 503


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8199)
