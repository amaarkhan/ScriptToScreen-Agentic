from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import chromadb


def _embed(text: str, dims: int = 24) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [digest[i] / 255.0 for i in range(dims)]


def _persist_collection(collection, item_id: str, request_id: str, payload: dict[str, Any]) -> None:
    serialized = json.dumps(payload, sort_keys=True)
    collection.add(
        ids=[item_id],
        documents=[serialized],
        embeddings=[_embed(serialized)],
        metadatas=[{"request_id": request_id}],
    )


def commit_memory_bundle(
    request_id: str,
    script: dict[str, Any],
    characters: list[dict[str, Any]],
    images: list[dict[str, Any]],
    memory_dir: str,
) -> dict[str, list[str]]:
    base = Path(memory_dir)
    base.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=base.as_posix())

    script_collection = client.get_or_create_collection(name="script_history")
    character_collection = client.get_or_create_collection(name="character_metadata")
    image_collection = client.get_or_create_collection(name="image_references")

    script_text = json.dumps(script, sort_keys=True)
    script_id = f"scr_{hashlib.sha256((request_id + script_text).encode('utf-8')).hexdigest()[:10]}"
    _persist_collection(script_collection, script_id, request_id, {"id": script_id, "request_id": request_id, "payload": script})

    character_ids: list[str] = []
    for item in characters:
        key = json.dumps(item, sort_keys=True)
        cid = f"chr_{hashlib.sha256((request_id + key).encode('utf-8')).hexdigest()[:10]}"
        character_ids.append(cid)
        _persist_collection(character_collection, cid, request_id, {"id": cid, "request_id": request_id, "payload": item})

    image_ids: list[str] = []
    for item in images:
        key = json.dumps(item, sort_keys=True)
        iid = f"img_{hashlib.sha256((request_id + key).encode('utf-8')).hexdigest()[:10]}"
        image_ids.append(iid)
        _persist_collection(image_collection, iid, request_id, {"id": iid, "request_id": request_id, "payload": item})

    return {
        "script_history_ids": [script_id],
        "character_memory_ids": character_ids,
        "image_memory_ids": image_ids,
    }