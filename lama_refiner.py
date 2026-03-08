import os
import cv2
import torch
import numpy as np
import requests
from PIL import Image
from tqdm import tqdm
import threading

class LaMaRefiner:
    def __init__(self, model_path="models/big-lama.pt"):
        self.model_path = model_path
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = None
        self._lock = threading.Lock()

    def _download_model(self, progress_callback=None):
        urls = [
            "https://huggingface.co/fashn-ai/LaMa/resolve/main/big-lama.pt?download=true",
            "https://github.com/Sanster/models/releases/download/add_big_lama/big-lama.pt"
        ]
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
        
        # Check for previous corrupted download (the 9-byte error file or similar)
        if os.path.exists(self.model_path) and os.path.getsize(self.model_path) < 100 * 1024 * 1024:
            print(f"Removing corrupted or incomplete model file ({os.path.getsize(self.model_path)} bytes): {self.model_path}")
            os.remove(self.model_path)

        if os.path.exists(self.model_path):
            return

        for url in urls:
            try:
                print(f"Attempting to download LaMa model from: {url}")
                response = requests.get(url, stream=True, timeout=30)
                response.raise_for_status()
                
                total_size = int(response.headers.get('content-length', 0))
                
                with open(self.model_path, "wb") as f, tqdm(
                    desc="Downloading big-lama.pt",
                    total=total_size,
                    unit='iB',
                    unit_scale=True,
                    unit_divisor=1024,
                ) as bar:
                    for data in response.iter_content(chunk_size=1024 * 1024): # 1MB chunks
                        size = f.write(data)
                        bar.update(size)
                        if progress_callback:
                            current = os.path.getsize(self.model_path)
                            progress_callback(current, total_size)
                
                # Verify downloaded size
                if os.path.getsize(self.model_path) > 100 * 1024 * 1024:
                    print("Download successful.")
                    return
                else:
                    print("Download failed: File size too small. Retrying with next source...")
                    if os.path.exists(self.model_path):
                        os.remove(self.model_path)
            except Exception as e:
                print(f"Error downloading from {url}: {e}")
                if os.path.exists(self.model_path):
                    os.remove(self.model_path)
                continue
        
        raise RuntimeError("Failed to download LaMa model from all sources.")

    def unload_model(self):
        with self._lock:
            if self.model is not None:
                print(f"Unloading LaMa model from {self.device}...")
                self.model = None
                if str(self.device).startswith("cuda"):
                    torch.cuda.empty_cache()
                import gc
                gc.collect()

    def load_model(self, progress_callback=None, force_device=None):
        with self._lock:  # Ensure atomic loading
            # If a specific device is requested and it's different from the current one, unload first
            if force_device is not None:
                new_device = torch.device(force_device)
                if self.model is not None and str(self.device) != str(new_device):
                    self.model = None # Force reload
                self.device = new_device

            if self.model is not None:
                return
            
            if not os.path.exists(self.model_path) or os.path.getsize(self.model_path) < 100 * 1024 * 1024:
                self._download_model(progress_callback=progress_callback)
                
            # Load model without CLI logging per user request
            self.model = torch.jit.load(self.model_path, map_location=self.device)
            self.model.eval()

    @torch.no_grad()
    def __call__(self, image: Image.Image, mask: Image.Image):
        self.load_model()
        
        # Convert PIL to OpenCV (BGR)
        img = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)
        mask = np.array(mask.convert("L"))
        
        # Preprocessing: Pad to multiples of 8
        h, w = img.shape[:2]
        pad_h = (8 - h % 8) % 8
        pad_w = (8 - w % 8) % 8
        
        img = cv2.copyMakeBorder(img, 0, pad_h, 0, pad_w, cv2.BORDER_REFLECT)
        mask = cv2.copyMakeBorder(mask, 0, pad_h, 0, pad_w, cv2.BORDER_REFLECT)
        
        # Prepare tensors
        img_tensor = torch.from_numpy(img).permute(2, 0, 1).unsqueeze(0).float().to(self.device) / 255.0
        mask_tensor = torch.from_numpy(mask).unsqueeze(0).unsqueeze(0).float().to(self.device) / 255.0
        
        # Inference
        result_tensor = self.model(img_tensor, mask_tensor)
        
        # Postprocessing
        result = result_tensor[0].permute(1, 2, 0).cpu().numpy()
        result = np.clip(result * 255.0, 0, 255).astype(np.uint8)
        
        # Crop back to original size
        result = result[:h, :w, :]
        
        # Convert back to PIL RGB
        return Image.fromarray(cv2.cvtColor(result, cv2.COLOR_BGR2RGB))

if __name__ == "__main__":
    import sys
    refiner = LaMaRefiner()
    refiner.load_model()
    print("Model ready.")
