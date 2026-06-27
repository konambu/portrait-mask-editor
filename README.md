# Pixel Art Portrait Mask Editor

An interactive web-based graphical user interface tool to refine transparency masks for pixel art portraits. 

This tool is especially useful in game development pipelines when AI-based background removers (like `rembg`) fail on white clothing, skin highlights, or fine details. By placing click markers, you can interactively guide a lineart-aware floodfill algorithm to correct transparency defects in real-time.

---

## Features

- **Interactive Canvas**: Place seed points directly on the high-resolution portrait.
  - **Left Click (Green Point)**: Forces the clicked region to be **Opaque** (restores shirts, sleeves, skin details).
  - **Right Click (Red Point)**: Forces the clicked region to be **Transparent** (removes off-white hair gaps or background corners).
- **Lineart-Aware Floodfill**: The BFS algorithm automatically spreads through pixels but stops perfectly at dark sketch lines/borders.
- **Dynamic Split View**: View the high-resolution transparent original image on the left, and a live downscaled pixelated transparency preview on the right.
- **ComfyUI Integration**: Clicking "Apply & Save" automatically copies the base image, queues the ComfyUI pixelation pipeline, applies the corrected transparency mask, and exports the final `.png` file directly to your game folder.

---

## Installation

### Prerequisites

Make sure Python 3.10+ is installed along with the following packages:

```bash
pip install numpy scipy pillow rembg
```

---

## Configuration

All paths and settings are configured in `config.json`. Create a file named `config.json` in the root folder of this project:

```json
{
    "port": 8000,
    "comfyui_url": "http://127.0.0.1:8188",
    "comfyui_input_dir": "C:\\Users\\<username>\\AppData\\Local\\Comfy-Desktop\\ComfyUI-Shared\\input",
    "comfyui_output_dir": "C:\\Users\\<username>\\AppData\\Local\\Comfy-Desktop\\ComfyUI-Shared\\output",
    "portrait_dir": "E:\\work\\new_game\\src\\test-game\\assets\\portraits"
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
