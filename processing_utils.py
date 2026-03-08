import os
from PIL import Image
from inverse_alpha_compositing import InverseAlphaCompositing
from lama_refiner import LaMaRefiner
import torch

_shared_processor = None

def get_shared_processor(use_gpu=True):
    """
    Returns a singleton instance of ProcessingUtils to avoid redundant model loads.
    Re-initializes if the requested use_gpu setting differs from the current instance.
    """
    global _shared_processor
    if _shared_processor is None:
        _shared_processor = ProcessingUtils(use_gpu=use_gpu)
    elif _shared_processor.use_gpu != (use_gpu and torch.cuda.is_available()):
        print(f"[PROCESSOR] Settings changed (GPU: {use_gpu}). Re-initializing...")
        _shared_processor = ProcessingUtils(use_gpu=use_gpu)
    return _shared_processor

def reset_shared_processor():
    """Explicitly clear the shared processor singleton."""
    global _shared_processor
    _shared_processor = None

class ProcessingUtils:
    def __init__(self, use_gpu=True):
        self.remover = InverseAlphaCompositing("sys_img/bg_48.png", "sys_img/bg_96.png")
        self.refiner = LaMaRefiner()
        self.use_gpu = use_gpu and torch.cuda.is_available()
        self.device = "cuda" if self.use_gpu else "cpu"
        self.refiner.load_model(force_device=self.device)

    def hybrid_process(self, img, logo_value=255.0, alpha_contrast=1.0, offset_x=0, offset_y=0, refine_extra=0.0):
        """
        Performs Hybrid removal: Inverse Alpha followed by LaMa Refinement.
        """
        # 1. Inverse Alpha Clean
        cleaned_img = self.remover.process_image(
            img, 
            logo_value=logo_value,
            alpha_contrast=alpha_contrast,
            offset_x=offset_x,
            offset_y=offset_y
        )
        
        # 2. LaMa Refine
        config = self.remover.detect_config(cleaned_img.width, cleaned_img.height)
        mask = Image.new("L", cleaned_img.size, 0)
        size = config["size"]
        dilation = int(size * (0.4 + refine_extra))
        expanded_size = size + 2 * dilation
        
        base_x = cleaned_img.width - config["margin_right"] - size + offset_x - dilation
        base_y = cleaned_img.height - config["margin_bottom"] - size + offset_y - dilation
        
        from PIL import ImageDraw
        draw = ImageDraw.Draw(mask)
        draw.rectangle([base_x, base_y, base_x + expanded_size, base_y + expanded_size], fill=255)
        
        final_img = self.refiner(cleaned_img, mask)
        return final_img

def save_with_metadata(p_img, original_img, output_path, extra_meta=None):
    """
    Saves image with preserved and extended metadata.
    """
    from PIL import PngImagePlugin
    
    meta = PngImagePlugin.PngInfo()
    # Strictly follow the injection method: Only preserve specific GemiPersona fields.
    whitelist = ["prompt", "url", "upload_path"]
    
    # 1. Preserve ONLY whitelisted fields from original
    for k, v in original_img.info.items():
        if k in whitelist:
            meta.add_text(k, str(v))
    
    # 2. Add/Override with extra_meta
    if extra_meta:
        for k, v in extra_meta.items():
            if k in whitelist:
                meta.add_text(k, str(v))
            
    # No EXIF preservation to avoid unnecessary elements.
    p_img.save(output_path, "PNG", pnginfo=meta)
