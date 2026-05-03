"""Higgsfield AI video generation integration."""

import asyncio
import httpx
from config import HIGGSFIELD_BASE_URL, HIGGSFIELD_API_ID, HIGGSFIELD_API_SECRET, SCENE_TYPE_MODEL_MAP


class VideoGenerator:
    def __init__(self, api_id: str = None, api_secret: str = None):
        self.api_id = api_id or HIGGSFIELD_API_ID
        self.api_secret = api_secret or HIGGSFIELD_API_SECRET
        self.base_url = HIGGSFIELD_BASE_URL

    @property
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_id}",
            "X-Api-Secret": self.api_secret,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def test_connection(self) -> dict:
        """Verify the Higgsfield API credentials are valid."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(f"{self.base_url}/v1/models", headers=self._headers)
                if r.status_code in (200, 201):
                    return {"ok": True}
                if r.status_code == 401:
                    return {"ok": False, "error": "Invalid API credentials"}
                # Many APIs return 404 for unknown routes but 401 for bad creds
                return {"ok": True, "note": f"API responded with {r.status_code}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def generate_video(
        self,
        prompt: str,
        model: str = "veo-3",
        duration: str = "10s",
        resolution: str = "720p",
        aspect_ratio: str = "16:9",
        reference_image_url: str = "",
    ) -> dict:
        """
        Submit a video generation job to Higgsfield.
        Returns {"job_id": str, "status": str} or raises on error.
        """
        duration_seconds = int(duration.replace("s", ""))

        payload = {
            "prompt": prompt,
            "model": model,
            "duration": duration_seconds,
            "resolution": resolution,
            "aspect_ratio": aspect_ratio,
        }
        if reference_image_url:
            payload["reference_image"] = reference_image_url

        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                f"{self.base_url}/v1/video/generate",
                headers=self._headers,
                json=payload,
            )
            if r.status_code not in (200, 201, 202):
                raise ValueError(f"Higgsfield API error {r.status_code}: {r.text}")
            data = r.json()
            job_id = data.get("id") or data.get("job_id") or data.get("generation_id", "")
            return {
                "job_id": job_id,
                "status": data.get("status", "pending"),
                "raw": data,
            }

    async def get_status(self, job_id: str) -> dict:
        """
        Poll the status of a generation job.
        Returns {"status": str, "video_url": str|None, "thumbnail_url": str|None}.
        """
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                f"{self.base_url}/v1/video/{job_id}",
                headers=self._headers,
            )
            if r.status_code == 404:
                return {"status": "not_found", "video_url": None}
            if r.status_code != 200:
                raise ValueError(f"Status check error {r.status_code}: {r.text}")
            data = r.json()
            return {
                "status":        data.get("status", "pending"),
                "video_url":     data.get("video_url") or data.get("output_url") or data.get("url"),
                "thumbnail_url": data.get("thumbnail_url") or data.get("thumbnail"),
                "raw":           data,
            }

    async def wait_for_completion(
        self,
        job_id: str,
        poll_interval: int = 10,
        max_wait: int = 600,
    ) -> dict:
        """Poll until completed or failed; raises on timeout."""
        elapsed = 0
        while elapsed < max_wait:
            result = await self.get_status(job_id)
            status = result["status"].lower()
            if status in ("completed", "done", "success", "finished"):
                return result
            if status in ("failed", "error", "cancelled"):
                raise ValueError(f"Generation failed: {result.get('raw', {})}")
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
        raise TimeoutError(f"Video generation timed out after {max_wait}s")

    @staticmethod
    def suggest_model(scene_type: str) -> str:
        """Return the recommended model slug for a given scene type."""
        return SCENE_TYPE_MODEL_MAP.get(scene_type, "veo-3")
