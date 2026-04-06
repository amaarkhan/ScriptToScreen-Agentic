# Phase 1 ComfyUI Setup (Teacher Requirement)

Phase 1 image generation is configured to require ComfyUI.
If `COMFYUI_URL` is not set or ComfyUI cannot generate, image generation fails intentionally.

## 1) Start ComfyUI Locally
Run your local ComfyUI server and make sure it is reachable from this machine.

Example URL:
- `http://127.0.0.1:8188`

## 2) Set COMFYUI_URL in PowerShell
```powershell
$env:COMFYUI_URL = "http://127.0.0.1:8188"
```

## 3) Verify Environment
```powershell
Write-Output $env:COMFYUI_URL
```

## 4) Run Phase 1
Use your normal Phase 1 acceptance runner.

## Notes
- Current adapter calls `POST {COMFYUI_URL}/generate` and expects JSON containing `image_base64`.
- If your ComfyUI instance does not expose `/generate`, run a small local bridge endpoint that maps to your ComfyUI workflow and returns `image_base64`.
