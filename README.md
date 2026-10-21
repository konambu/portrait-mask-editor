# Pixel Art Portrait Mask Editor

An interactive local browser tool for refining transparency masks for pixel art portraits. A Python HTTP backend combines rembg segmentation, near-white corner flood fill, and user-provided opaque/transparent seed points. Final export uses a ComfyUI pixelation workflow.

Designed for game-art workflows where automatic background removal loses white clothing, skin highlights, or fine details. Seed edits are applied when you click **Update Preview**, not continuously on every click.

---

## Features

- **Interactive Canvas**: Place seed points directly on the high-resolution portrait.
  - **Left Click (Green Point)**: Forces the clicked region to be **Opaque** (restores shirts, sleeves, skin details).
  - **Right Click (Red Point)**: Forces the clicked region to be **Transparent** (removes off-white hair gaps or background corners).
- **Brightness-Based Floodfill**: Opaque seeds spread through pixels with mean RGB brightness above 90; transparent seeds spread above 220. Dark outlines can limit spread, but this is a heuristic, not guaranteed edge detection.
- **Dynamic Split View**: View the high-resolution transparent original image on the left, and a live downscaled pixelated transparency preview on the right.
- **ComfyUI Integration**: Clicking "Apply & Save" automatically copies the base image, queues the ComfyUI pixelation pipeline, applies the corrected transparency mask, and exports the final `.png` file directly to your game folder.

---

## Installation

### Prerequisites

Use a Python environment compatible with NumPy, SciPy, Pillow and rembg, including a working ONNX runtime for rembg. There is no requirements manifest, lockfile, or tested Python-version matrix in this repository. From the repository directory, a manual setup is:

```bash
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install numpy scipy pillow rembg
```

The commands above are for Windows PowerShell. Activate that environment before using `python` below, or substitute `.\.venv\Scripts\python.exe`. A rembg-compatible ONNX runtime must also be available; package installation alone is not an end-to-end validation.

Preview uses rembg's `isnet-general-use` model. First use may need network access to download model weights. Saving additionally requires a running ComfyUI instance with the custom `PixelArtNode` node installed. That node's implementation and installation instructions are not included here. The queued workflow uses `LoadImage`, `PixelArtNode` (`num_colors=48`, `pixel_size=3`), and `SaveImage`.

---

## Configuration

Edit the included `config.json` in the repository root. It and the fallback values in the script contain machine-specific paths; replace them before opening the UI. All directories must already exist. For example:

```json
{
    "port": 8000,
    "comfyui_url": "http://127.0.0.1:8188",
    "comfyui_input_dir": "C:/path/to/ComfyUI/input",
    "comfyui_output_dir": "C:/path/to/ComfyUI/output",
    "portrait_dir": "C:/path/to/portrait-copies"
}
```

### Settings Description
- `port`: Local port to run the web server on (default: `8000`).
- `comfyui_url`: The URL of your running ComfyUI server instance.
- `comfyui_input_dir` / `comfyui_output_dir`: Shared input/output paths for ComfyUI to read/write images.
- `portrait_dir`: The destination directory where your base portraits (`<char>_base.png`) are stored and where the finished transparent outputs (`<char>.png`) will be exported.

---

## Usage

1. Start the server:
   ```bash
   python portrait_editor.py
   ```
2. Open your browser and navigate to: **[http://localhost:8000](http://localhost:8000)**
3. Choose the portrait you want to edit from the sidebar dropdown.
4. Click on the image to place opaque/transparent points.
5. Click **"Update Preview"** to see your live preview.
6. Click **"Apply & Save"** to compile and export the finalized texture.

Use copies of your portraits first. Saving overwrites `<char>.png` without a backup or undo and copies `<char>_base.png` into the configured ComfyUI input directory (overwriting a same-name file there). It also creates ComfyUI output files. The original base portrait in `portrait_dir` is not modified. Seed points are in-memory only and reset on portrait selection; remove individual seeds or use **Clear All**, then update the preview again. Stop the server with Ctrl+C.

## Code Map

| File | Responsibility |
| --- | --- |
| `portrait_editor.py` | Configuration, mask algorithms, HTTP handlers, rembg inference, ComfyUI queue/history polling, PNG export |
| `editor_assets/index.html` | Browser UI, image overlays, seed editing, preview/save requests |
| `config.json` | Server port, ComfyUI URL/directories, portrait directory |

## Limitations And Validation

- This is a trusted-local prototype, not a public service. The server currently binds all interfaces, not just localhost, and has no authentication or robust request/path validation. Use a trusted machine/network and firewall it from remote access.
- Only immediate files named `<char>_base.png` are listed; no recursive scanning or file-upload UI is implemented.
- Mask correction includes hard-coded coordinate heuristics (350, 1300, 1200) and a fixed 3-pixel grid. Different portrait sizes/compositions can require algorithm changes. Preview pixelation uses nearest-neighbor resizing, not ComfyUI's final color quantization, so preview and export may differ.
- The HTTP server is single-threaded. Each preview/save creates a rembg session, and save waits synchronously for ComfyUI with no completion timeout. Missing/failed workflows can leave the UI waiting and block other requests; stop the server to interrupt it.
- ComfyUI input/output directories must be accessible on this machine and correspond to those used by the configured ComfyUI server. Export assumes matching image dimensions.
- Configuration is tracked in Git. Ignore rules do not conceal edits to it; review local paths before sharing changes.
- No automated test suite or CI configuration is included. A dependency-free, non-mutating syntax check is:

  ```powershell
  python -B -c "import ast, pathlib; ast.parse(pathlib.Path('portrait_editor.py').read_text(encoding='utf-8')); print('Syntax OK')"
  ```

  Syntax validation does not exercise inference, the browser, custom nodes, or saving. End-to-end testing requires the model, configured directories, and ComfyUI; test only against disposable portrait copies.
