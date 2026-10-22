#!/usr/bin/env python3
"""Run a page image through the baidu/Unlimited-OCR Hugging Face Space (ZeroGPU demo).

Drives the Space's public Gradio API directly over HTTP (upload -> call -> SSE),
which is more robust against Gradio 6 schema changes than gradio_client's
endpoint resolution. No local GPU required.

Usage:
  python3 eval/run_ocr_space.py <local-image-path> <mode> <out-txt>
Modes: base (accurate, 1024px) | gundam (fast, 640px crop)
"""
import json
import os
import sys
import time
import urllib.request

BASE = "https://baidu-unlimited-ocr.hf.space/gradio_api"

# Authenticating with an HF token raises the ZeroGPU quota substantially.
# If set, both the upload and the call carry the token.
HF_TOKEN = os.environ.get("HF_TOKEN")


def _headers(extra: dict | None = None) -> dict:
    h = dict(extra or {})
    if HF_TOKEN:
        h["Authorization"] = f"Bearer {HF_TOKEN}"
    return h


def upload(path: str) -> tuple[str, int]:
    with open(path, "rb") as f:
        png = f.read()
    boundary = "----vibeBoundary7f3d"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="files"; filename="{os.path.basename(path)}"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    ).encode() + png + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        BASE + "/upload", data=body,
        headers=_headers({"Content-Type": f"multipart/form-data; boundary={boundary}"}),
    )
    server_path = json.loads(urllib.request.urlopen(req, timeout=120).read())[0]
    return server_path, len(png)


def run_ocr(image_path: str, size: int, mode: str) -> str:
    payload = {
        "data": [
            {
                "path": image_path,
                "url": None,
                "size": size,
                "orig_name": os.path.basename(image_path),
                "mime_type": "image/png",
                "is_stream": False,
                "meta": {"_type": "gradio.FileData"},
            },
            mode,
            "document parsing.",
        ]
    }
    req = urllib.request.Request(
        BASE + "/call/run_ocr",
        data=json.dumps(payload).encode(),
        headers=_headers({"Content-Type": "application/json"}),
    )
    event_id = json.loads(urllib.request.urlopen(req, timeout=60).read())["event_id"]

    final = ""
    t0 = time.time()
    event = None
    with urllib.request.urlopen(f"{BASE}/call/run_ocr/{event_id}", timeout=900) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").rstrip("\n")
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
                if event == "error":
                    raise RuntimeError("space error (often ZeroGPU quota); see data line")
            elif line.startswith("data:") and event in ("generating", "complete"):
                data = line.split(":", 1)[1].strip()
                try:
                    obj = json.loads(data)
                    chunk = obj[0] if isinstance(obj, list) and obj else obj
                    if isinstance(chunk, dict):
                        chunk = chunk.get("text", "")
                    if chunk:
                        final = chunk
                        print(f"\r[stream] {len(final)} chars, {time.time()-t0:.0f}s", end="")
                except (ValueError, TypeError):
                    pass
                if event == "complete":
                    break
    print()
    return final


def main() -> int:
    image, mode, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    print(f"[ocr] space=baidu/Unlimited-OCR mode={mode} image={image}")
    server_path, size = upload(image)
    print(f"[ocr] uploaded -> {server_path}")
    final = run_ocr(server_path, size, mode)
    if not final:
        sys.exit("[ocr] empty result")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(final)
    print(f"[ocr] wrote {out_path} ({len(final)} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
