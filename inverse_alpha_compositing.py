import numpy as np
from PIL import Image
import os

class InverseAlphaCompositing:
    def __init__(self, bg_48_path, bg_96_path):
        self.bg_captures = {
            48: self._load_image(bg_48_path),
            96: self._load_image(bg_96_path)
        }
        self.alpha_maps = {}

    def _load_image(self, path):
        if not os.path.exists(path):
            raise FileNotFoundError(f"Asset not found: {path}")
        return Image.open(path).convert("RGB")

    def get_alpha_map(self, size, contrast=1.0):
        # We don't cache with contrast because user might change it
        bg_img = self.bg_captures[size]
        bg_data = np.array(bg_img).astype(np.float32)
        
        # Calculate alpha map: max(R, G, B) / 255.0
        alpha_map = np.max(bg_data, axis=2) / 255.0
        
        # Apply alpha contrast/multiplier
        if contrast != 1.0:
            alpha_map = np.clip(alpha_map * contrast, 0, 1.0)
            
        return alpha_map

    def detect_config(self, width, height):
        if width > 1024 and height > 1024:
            return {"size": 96, "margin_right": 64, "margin_bottom": 64}
        else:
            return {"size": 48, "margin_right": 32, "margin_bottom": 32}

    def process_image(self, pil_img, logo_value=255.0, alpha_contrast=1.0, offset_x=0, offset_y=0):
        original_mode = pil_img.mode
        img = pil_img.convert("RGB")
        width, height = img.size
        
        config = self.detect_config(width, height)
        size = config["size"]
        
        # Calculate base position
        base_x = width - config["margin_right"] - size
        base_y = height - config["margin_bottom"] - size
        
        # Apply user offsets
        x = base_x + offset_x
        y = base_y + offset_y
        
        # Boundary check for safety
        x = np.clip(x, 0, width - size)
        y = np.clip(y, 0, height - size)
        
        img_data = np.array(img).astype(np.float32)
        roi = img_data[y:y+size, x:x+size]
        
        alpha = self.get_alpha_map(size, contrast=alpha_contrast)
        alpha_3d = alpha[:, :, np.newaxis]
        
        ALPHA_THRESHOLD = 0.002
        MAX_ALPHA = 0.99
        
        constrained_alpha = np.clip(alpha_3d, 0, MAX_ALPHA)
        mask = alpha_3d >= ALPHA_THRESHOLD
        
        divisor = 1.0 - constrained_alpha
        restored_roi = np.where(
            mask,
            (roi - constrained_alpha * logo_value) / divisor,
            roi
        )
        
        restored_roi = np.clip(np.round(restored_roi), 0, 255).astype(np.uint8)
        
        img_data_uint8 = np.array(img)
        img_data_uint8[y:y+size, x:x+size] = restored_roi
        
        result = Image.fromarray(img_data_uint8)
        if original_mode == "RGBA":
            return result.convert("RGBA")
        return result

if __name__ == "__main__":
    remover = InverseAlphaCompositing("sys_img/bg_48.png", "sys_img/bg_96.png")
