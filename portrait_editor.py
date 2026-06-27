import os
import time
import json
import base64
import shutil
import urllib.request
from io import BytesIO
from http.server import HTTPServer, BaseHTTPRequestHandler
import numpy as np
from PIL import Image
from scipy.ndimage import label, find_objects, minimum_filter
from rembg import remove, new_session

# Load configuration
config_path = os.path.join(os.path.dirname(__file__), "config.json")
config = {
    "port": 8000,
    "comfyui_url": "http://127.0.0.1:8188",
    "comfyui_input_dir": r"C:\Users\nanbu\AppData\Local\Comfy-Desktop\ComfyUI-Shared\input",
    "comfyui_output_dir": r"C:\Users\nanbu\AppData\Local\Comfy-Desktop\ComfyUI-Shared\output",
    "portrait_dir": r"E:\work\new_game\src\test-game\assets\portraits"
}
if os.path.exists(config_path):
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config.update(json.load(f))
    except Exception as e:
        print(f"Failed to load config.json, using defaults: {e}")

PORT = config["port"]
comfy_url = config["comfyui_url"]
comfy_input_dir = config["comfyui_input_dir"]
comfy_output_dir = config["comfyui_output_dir"]
portrait_dir = config["portrait_dir"]
editor_assets_dir = os.path.join(os.path.dirname(__file__), "editor_assets")

def queue_comfy_pixelation(char_name, base_file):
    wf = {
        "1": {"class_type": "LoadImage", "inputs": {"image": base_file}},
        "2": {"class_type": "PixelArtNode", "inputs": {"image": ["1", 0], "num_colors": 48, "pixel_size": 3}},
        "3": {"class_type": "SaveImage", "inputs": {"images": ["2", 0], "filename_prefix": f"transparent_output/{char_name}_opaque_pixel"}}
    }
    data = json.dumps({"prompt": wf}).encode('utf-8')
    req = urllib.request.Request(f"{comfy_url}/prompt", data=data, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req) as response:
        res = json.loads(response.read().decode('utf-8'))
        return res.get("prompt_id")

def get_comfy_history(prompt_id):
    try:
        req = urllib.request.Request(f"{comfy_url}/history/{prompt_id}")
        with urllib.request.urlopen(req) as response:
            res = json.loads(response.read().decode('utf-8'))
            return res.get(prompt_id)
    except Exception:
        return None

def flood_fill_corners(img_np, tolerance=15):
    h, w, _ = img_np.shape
    mask = np.zeros((h, w), dtype=np.uint8)
    target_color = np.array([255, 255, 255], dtype=np.int32)
    queue = []
    
    # Corners
    corners = [(0, 0), (0, w-1), (h-1, 0), (h-1, w-1)]
    for y, x in corners:
        diff = np.abs(img_np[y, x] - target_color)
        if np.all(diff <= tolerance):
            queue.append((y, x))
            mask[y, x] = 1
            
    head = 0
    while head < len(queue):
        cy, cx = queue[head]
        head += 1
        
        for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            ny, nx = cy + dy, cx + dx
            if 0 <= ny < h and 0 <= nx < w:
                if mask[ny, nx] == 0:
                    diff = np.abs(img_np[ny, nx] - target_color)
                    if np.all(diff <= tolerance):
                        mask[ny, nx] = 1
                        queue.append((ny, nx))
    return mask

def run_seed_floodfill(img_np, start_x, start_y, fill_type):
    """
    Runs a lineart-aware floodfill from a user-clicked seed.
    If fill_type == 'opaque': spreads to non-lineart pixels (brightness > 90).
    If fill_type == 'transparent': spreads to light/background pixels (brightness > 220).
    """
    h, w, _ = img_np.shape
    mask = np.zeros((h, w), dtype=np.uint8)
    
    if not (0 <= start_x < w and 0 <= start_y < h):
        return mask
        
    queue = [(start_y, start_x)]
    mask[start_y, start_x] = 1
    
    head = 0
    while head < len(queue):
        cy, cx = queue[head]
        head += 1
        
        for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            ny, nx = cy + dy, cx + dx
            if 0 <= ny < h and 0 <= nx < w:
                if mask[ny, nx] == 0:
                    r, g, b = img_np[ny, nx]
                    brightness = (int(r) + int(g) + int(b)) / 3.0
                    
                    should_spread = False
                    if fill_type == "opaque":
                        # Spreads through skin, clothes, shading but stops at dark lineart outlines (brightness <= 90)
                        if brightness > 90:
                            should_spread = True
                    else:
                        # Spreads through white background/gaps (brightness > 220)
                        if brightness > 220:
                            should_spread = True
                            
                    if should_spread:
                        mask[ny, nx] = 1
                        queue.append((ny, nx))
    return mask

def generate_corrected_mask(img_np, raw_alpha, seeds):
    h, w, _ = img_np.shape
    
    # 1. Base corner-fill background mask
    flood_mask = flood_fill_corners(img_np, tolerance=15)
    
    # 2. Label transparent parts of raw rembg mask
    binary_trans = raw_alpha <= 127
    labeled_im, num_labels = label(binary_trans)
    
    border_labels = set()
    for x in range(w):
        border_labels.add(labeled_im[0, x])
        border_labels.add(labeled_im[h-1, x])
    for y in range(h):
        border_labels.add(labeled_im[y, 0])
        border_labels.add(labeled_im[y, w-1])
        
    slices = find_objects(labeled_im)
    
    # Start with fully opaque
    corrected_alpha = np.ones((h, w), dtype=np.uint8) * 255
    
    # Apply floodfill background
    corrected_alpha[flood_mask == 1] = 0
    
    # Re-apply transparent gaps from rembg
    for idx in range(1, num_labels + 1):
        sl = slices[idx - 1]
        if sl is not None:
            ymin, ymax = sl[0].start, sl[0].stop
            xmin, xmax = sl[1].start, sl[1].stop
            cx = xmin + (xmax - xmin) / 2
            cy = ymin + (ymax - ymin) / 2
            
            is_background_gap = False
            if idx in border_labels:
                component_pixels = labeled_im == idx
                if np.any((flood_mask == 1) & component_pixels):
                    is_background_gap = True
            else:
                # Hair gaps on sides are kept transparent
                if not (350 <= cx <= 1300 or cy > 1200):
                    is_background_gap = True
                    
            if is_background_gap:
                corrected_alpha[labeled_im == idx] = 0
                
    # 3. Apply user-defined seeds
    for seed in seeds:
        sx, sy = seed['x'], seed['y']
        stype = seed['type']
        
        seed_mask = run_seed_floodfill(img_np, sx, sy, stype)
        if stype == "opaque":
            corrected_alpha[seed_mask == 1] = 255
        else:
            corrected_alpha[seed_mask == 1] = 0
            
    # Apply minimum filter to keep clean details
    corrected_alpha_min = minimum_filter(corrected_alpha, size=3)
    
    # Scale to match pixel size (3)
    pixel_size = 3
    alpha_img = Image.fromarray(corrected_alpha_min)
    small = alpha_img.resize((int(w / pixel_size), int(h / pixel_size)), Image.Resampling.NEAREST)
    pixelated_alpha = small.resize((w, h), Image.Resampling.NEAREST)
    
    return np.where(np.array(pixel_size_check(pixelated_alpha)) > 127, 255, 0).astype(np.uint8)

def pixel_size_check(img):
    return img.convert("L")

class EditorHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass # Suppress logging to keep console clean

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            with open(os.path.join(editor_assets_dir, "index.html"), "rb") as f:
                self.wfile.write(f.read())
                
        elif self.path == "/api/list":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            
            # List characters ending with _base.png
            files = [f[:-9] for f in os.listdir(portrait_dir) if f.endswith("_base.png")]
            self.wfile.write(json.dumps(files).encode('utf-8'))
            
        elif self.path.startswith("/api/original"):
            # Serve original _base.png
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            name = query.get("name", [""])[0]
            file_path = os.path.join(portrait_dir, f"{name}_base.png")
            
            if os.path.exists(file_path):
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.end_headers()
                with open(file_path, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(404, "File not found")
                
        elif self.path.startswith("/api/processed"):
            # Serve current output portrait
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            name = query.get("name", [""])[0]
            file_path = os.path.join(portrait_dir, f"{name}.png")
            
            if os.path.exists(file_path):
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.end_headers()
                with open(file_path, "rb") as f:
                    self.wfile.write(f.read())
            else:
                # Fallback to original
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.end_headers()
                with open(os.path.join(portrait_dir, f"{name}_base.png"), "rb") as f:
                    self.wfile.write(f.read())
        else:
            self.send_error(404, "Not found")

    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8'))
        
        name = data.get("name")
        seeds = data.get("seeds", [])
        
        base_path = os.path.join(portrait_dir, f"{name}_base.png")
        if not os.path.exists(base_path):
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "error": "Character not found"}).encode('utf-8'))
            return
            
        img = Image.open(base_path).convert("RGB")
        img_np = np.array(img)
        h, w, _ = img_np.shape
        
        # 1. Run rembg to extract raw mask
        session = new_session("isnet-general-use")
        rgba_base = remove(img, session=session, post_process_mask=False)
        alpha_np = np.array(rgba_base)[:, :, 3]
        
        # 2. Correct mask using corner flood fill and user seed points
        mask_np = generate_corrected_mask(img_np, alpha_np, seeds)
        
        if self.path == "/api/process":
            # Fast Local Live Preview (using PIL downscaling to pixelate colors)
            pixel_size = 3
            img_pixel = img.resize((int(w / pixel_size), int(h / pixel_size)), Image.Resampling.NEAREST)
            img_pixel_up = img_pixel.resize((w, h), Image.Resampling.NEAREST)
            
            final_rgba = Image.merge("RGBA", (*img_pixel_up.split(), Image.fromarray(mask_np)))
            
            # Encode as base64
            buffered = BytesIO()
            final_rgba.save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
            
            # Generate high-res transparent image for the left canvas click target
            highres_rgba = Image.merge("RGBA", (*img.split(), Image.fromarray(mask_np)))
            buffered_hr = BytesIO()
            highres_rgba.save(buffered_hr, format="PNG")
            img_hr_str = base64.b64encode(buffered_hr.getvalue()).decode('utf-8')
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": True, 
                "image_b64": img_str,
                "highres_b64": img_hr_str
            }).encode('utf-8'))
            
        elif self.path == "/api/save":
            # Save final image by triggering ComfyUI pixelation
            base_file = f"{name}_base.png"
            shutil.copy(base_path, os.path.join(comfy_input_dir, base_file))
            
            print(f"[{name}] Triggering ComfyUI for save...")
            prompt_id = queue_comfy_pixelation(name, base_file)
            
            opaque_pixel_path = None
            while True:
                hist = get_comfy_history(prompt_id)
                if hist and hist.get("status", {}).get("completed", False):
                    outputs = hist.get("outputs", {})
                    for node_id, output_data in outputs.items():
                        if "images" in output_data:
                            for img_info in output_data["images"]:
                                filename = img_info["filename"]
                                subfolder = img_info.get("subfolder", "")
                                opaque_pixel_path = os.path.join(comfy_output_dir, subfolder, filename)
                    break
                time.sleep(1)
                
            if not opaque_pixel_path or not os.path.exists(opaque_pixel_path):
                # Fallback to latest output matching pattern
                import glob
                pattern = os.path.join(comfy_output_dir, "transparent_output", f"{name}_opaque_pixel_*.png")
                files = glob.glob(pattern)
                if files:
                    files.sort(key=os.path.getmtime)
                    opaque_pixel_path = files[-1]
                else:
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"success": False, "error": "Could not fetch pixelated image from ComfyUI"}).encode('utf-8'))
                    return
            
            img_pixel = Image.open(opaque_pixel_path).convert("RGB")
            final_rgba = Image.merge("RGBA", (*img_pixel.split(), Image.fromarray(mask_np)))
            
            dest_path = os.path.join(portrait_dir, f"{name}.png")
            final_rgba.save(dest_path)
            print(f"[{name}] Corrected and pixelated portrait saved to {dest_path}")
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True}).encode('utf-8'))

def run_server():
    server_address = ('', PORT)
    httpd = HTTPServer(server_address, EditorHandler)
    print(f"\n==================================================")
    print(f" Portrait Mask Editor Server running at:")
    print(f" http://localhost:{PORT}")
    print(f"==================================================\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        httpd.server_close()

if __name__ == "__main__":
    run_server()
