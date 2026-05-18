"""
Gemini API Image Generation Client
Direct API-based image generation — bypasses the browser engine entirely.
"""
import os
import io
import time
import asyncio
import threading
from datetime import datetime
from PIL import Image


class GeminiAPIClient:
    """Wraps the google-genai SDK for direct Gemini API image generation."""

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash-image"):
        from google import genai
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self._lock = threading.Lock()
        self._stats = {
            "cycles": 0,
            "successes": 0,
            "failures": 0,
            "refused": 0,
            "is_running": False,
            "start_time": None,
        }
        self._stop_event = threading.Event()

    # ── Stats ───────────────────────────────────────────────────────────────
    def get_stats(self) -> dict:
        with self._lock:
            return dict(self._stats)

    def reset_stats(self):
        with self._lock:
            self._stats = {
                "cycles": 0,
                "successes": 0,
                "failures": 0,
                "refused": 0,
                "is_running": False,
                "start_time": None,
            }

    # ── Single Image Generation ─────────────────────────────────────────────
    async def generate_image(
        self,
        prompt: str,
        save_dir: str,
        naming_cfg: dict,
        extra_meta: dict | None = None,
        reference_image_path: str | None = None,
    ) -> dict:
        """
        Generate a single image via Gemini API.

        naming_cfg: {prefix: str, padding: int, start: int}
        extra_meta: {prompt: str, ...} — embedded in PNG metadata

        Returns:
            {"status": "success", "saved_paths": [...], "next_start": int}
            {"status": "refused", "reason": "..."}
            {"status": "error",   "message": "..."}
        """
        try:
            contents = [prompt]

            # Optional: attach reference image for editing
            if reference_image_path and os.path.exists(reference_image_path):
                ref_img = Image.open(reference_image_path)
                contents.append(ref_img)

            # Run SDK call in a thread to avoid blocking the event loop
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model,
                contents=contents,
            )

            # Parse response — extract images
            os.makedirs(save_dir, exist_ok=True)
            saved_paths = []

            prefix = naming_cfg.get("prefix", "")
            padding = naming_cfg.get("padding", 2)
            start_idx = naming_cfg.get("start", 1)

            for part in response.parts:
                if part.inline_data is not None:
                    image = part.as_image()

                    # Find next available filename (same logic as browser_engine)
                    while True:
                        save_name = f"{prefix}{str(start_idx).zfill(padding)}.png"
                        save_path = os.path.join(save_dir, save_name)
                        if not os.path.exists(save_path):
                            break
                        start_idx += 1

                    # Save with metadata
                    self._save_with_meta(image, save_path, extra_meta)
                    saved_paths.append(save_path)
                    start_idx += 1

            if saved_paths:
                with self._lock:
                    self._stats["successes"] += 1
                    self._stats["cycles"] += 1
                return {
                    "status": "success",
                    "saved_paths": saved_paths,
                    "next_start": start_idx,
                }
            else:
                # No image in response = refused / safety blocked
                text_parts = [p.text for p in response.parts if p.text]
                reason = " ".join(text_parts) if text_parts else "No image returned"
                with self._lock:
                    self._stats["refused"] += 1
                    self._stats["cycles"] += 1
                return {"status": "refused", "reason": reason}

        except Exception as e:
            error_msg = str(e)
            with self._lock:
                self._stats["failures"] += 1
                self._stats["cycles"] += 1
                # Classify safety blocks as refusals
                if any(kw in error_msg.upper() for kw in ["SAFETY", "BLOCKED", "RECITATION"]):
                    self._stats["refused"] += 1
            return {"status": "error", "message": error_msg}

    # ── Watermark Removal (reuses project pipeline) ─────────────────────────
    @staticmethod
    def process_watermark(saved_paths: list, save_dir: str, use_gpu: bool = True):
        """
        Runs the existing LaMa-based watermark removal on the given paths.
        Returns list of processed output paths.
        """
        from processing_utils import get_shared_processor, save_with_metadata
        processor = get_shared_processor(use_gpu=use_gpu)
        p_dir = os.path.join(save_dir, "processed")
        os.makedirs(p_dir, exist_ok=True)

        processed = []
        for p_in in saved_paths:
            if os.path.exists(p_in):
                try:
                    with Image.open(p_in) as img:
                        final_img = processor.hybrid_process(img)
                        p_path = os.path.join(p_dir, os.path.basename(p_in))
                        save_with_metadata(final_img, img, p_path)
                        processed.append(p_path)
                except Exception as e:
                    print(f"[API_GEN] Watermark removal failed for {p_in}: {e}")
        return processed

    # ── Stop Signal ─────────────────────────────────────────────────────────
    def request_stop(self):
        self._stop_event.set()

    def is_stop_requested(self) -> bool:
        return self._stop_event.is_set()

    def clear_stop(self):
        self._stop_event.clear()
        with self._lock:
            self._stats["is_running"] = False

    # ── Internal: Save PNG with metadata ────────────────────────────────────
    @staticmethod
    def _save_with_meta(pil_img: Image.Image, output_path: str, meta: dict | None):
        """Save image as PNG with embedded text metadata."""
        from PIL import PngImagePlugin
        info = PngImagePlugin.PngInfo()
        if meta:
            for k, v in meta.items():
                if k in ("aspect_ratio", "prompt", "url", "upload_path", "model", "source"):
                    info.add_text(k, str(v))
        # Always tag source
        info.add_text("source", "gemini_api")
        pil_img.save(output_path, "PNG", pnginfo=info)
