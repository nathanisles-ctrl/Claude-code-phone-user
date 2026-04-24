import asyncio
import logging
import time
from pathlib import Path
from typing import Optional
import httpx
from config import settings

logger = logging.getLogger(__name__)

# Higgsfield API base URL — update if their docs specify a different version path
HIGGSFIELD_BASE = settings.HIGGSFIELD_BASE_URL.rstrip("/")

# Model ID mapping (Higgsfield model slugs — verify against their live docs)
MODEL_SLUGS = {
    "veo3": "veo-3",
    "seedance2": "seedance-2",
    "kling3": "kling-3.0",
    "sora2": "sora-2",
    "higgsfield": "higgsfield-1",
    "auto": "higgsfield-1",
}

RESOLUTION_MAP = {
    "480p": {"width": 854, "height": 480},
    "720p": {"width": 1280, "height": 720},
    "1080p": {"width": 1920, "height": 1080},
    "4k": {"width": 3840, "height": 2160},
}


def _auth_headers() -> dict:
    """Build Higgsfield authentication headers."""
    return {
        "x-api-id": settings.HIGGSFIELD_API_ID,
        "x-api-secret": settings.HIGGSFIELD_API_SECRET,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def suggest_model(scene_type: str) -> str:
    """Return the best model slug for a given scene type."""
    model_key = settings.SCENE_TYPE_TO_MODEL.get(scene_type, "higgsfield")
    return MODEL_SLUGS.get(model_key, "higgsfield-1")


async def start_generation(
    prompt: str,
    model: str = "auto",
    duration: int = 5,
    resolution: str = "1080p",
    reference_image_urls: Optional[list[str]] = None,
    negative_prompt: str = "",
) -> dict:
    """
    Submit a video generation job to Higgsfield.
    Returns the raw API response containing the job ID.
    """
    res = RESOLUTION_MAP.get(resolution, RESOLUTION_MAP["1080p"])
    model_slug = MODEL_SLUGS.get(model, model) if model != "auto" else "higgsfield-1"

    payload: dict = {
        "prompt": prompt,
        "model": model_slug,
        "duration": duration,
        "width": res["width"],
        "height": res["height"],
    }
    if negative_prompt:
        payload["negative_prompt"] = negative_prompt
    if reference_image_urls:
        payload["reference_images"] = reference_image_urls

    logger.info("Submitting Higgsfield generation: model=%s prompt='%.80s'", model_slug, prompt)

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{HIGGSFIELD_BASE}/v1/video/generate",
            headers=_auth_headers(),
            json=payload,
        )
        if resp.status_code == 401:
            raise ValueError("Higgsfield authentication failed — check API ID and Secret")
        resp.raise_for_status()
        data = resp.json()
        logger.info("Generation job created: %s", data.get("id") or data.get("job_id"))
        return data


async def get_generation_status(job_id: str) -> dict:
    """Poll for a job's current status."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{HIGGSFIELD_BASE}/v1/video/generations/{job_id}",
            headers=_auth_headers(),
        )
        resp.raise_for_status()
        return resp.json()


async def wait_for_completion(
    job_id: str,
    timeout_seconds: int = 600,
    poll_interval: int = 10,
    progress_callback=None,
) -> dict:
    """
    Poll until the job completes or times out.
    Returns the final status dict which contains the video URL.
    """
    deadline = time.time() + timeout_seconds
    attempt = 0
    while time.time() < deadline:
        await asyncio.sleep(poll_interval)
        attempt += 1
        try:
            status = await get_generation_status(job_id)
        except httpx.HTTPError as exc:
            logger.warning("Poll attempt %d failed: %s", attempt, exc)
            continue

        state = (status.get("status") or status.get("state") or "").lower()
        logger.debug("Job %s status: %s (attempt %d)", job_id, state, attempt)

        if progress_callback:
            await progress_callback(state, attempt)

        if state in ("completed", "succeeded", "done", "finished"):
            return status
        if state in ("failed", "error", "cancelled"):
            error_msg = status.get("error") or status.get("message") or "Generation failed"
            raise RuntimeError(f"Higgsfield generation failed: {error_msg}")

    raise TimeoutError(f"Generation timed out after {timeout_seconds}s (job {job_id})")


async def download_video(video_url: str, output_path: Path) -> Path:
    """Download the finished video to output_path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading video from %s → %s", video_url, output_path)
    async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
        async with client.stream("GET", video_url) as resp:
            resp.raise_for_status()
            with open(output_path, "wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=8192):
                    f.write(chunk)
    logger.info("Video saved: %s (%.1f MB)", output_path, output_path.stat().st_size / 1_000_000)
    return output_path


def extract_video_url(status: dict) -> str:
    """Extract the video download URL from a completed status response."""
    for key in ("video_url", "url", "output_url", "download_url", "result_url"):
        url = status.get(key)
        if url:
            return url
    # Some APIs nest it
    output = status.get("output") or status.get("result") or {}
    if isinstance(output, dict):
        for key in ("video_url", "url"):
            url = output.get(key)
            if url:
                return url
    if isinstance(output, str) and output.startswith("http"):
        return output
    raise ValueError(f"Could not find video URL in status response: {list(status.keys())}")


async def generate_video_full(
    prompt: str,
    output_path: Path,
    model: str = "auto",
    duration: int = 5,
    resolution: str = "1080p",
    reference_image_urls: Optional[list[str]] = None,
    progress_callback=None,
) -> Path:
    """
    End-to-end: submit → poll → download.
    Returns the local path of the downloaded video.
    """
    submission = await start_generation(
        prompt=prompt,
        model=model,
        duration=duration,
        resolution=resolution,
        reference_image_urls=reference_image_urls,
    )
    job_id = submission.get("id") or submission.get("job_id") or submission.get("generation_id")
    if not job_id:
        raise ValueError(f"No job ID in Higgsfield response: {submission}")

    final_status = await wait_for_completion(
        job_id=job_id,
        progress_callback=progress_callback,
    )
    video_url = extract_video_url(final_status)
    return await download_video(video_url, output_path)


async def list_available_models() -> list[dict]:
    """Return Higgsfield's available model list."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{HIGGSFIELD_BASE}/v1/models",
            headers=_auth_headers(),
        )
        if resp.is_error:
            # Fallback to static list if endpoint doesn't exist
            return [
                {"id": slug, "name": info["name"], "scene_types": info["scene_types"]}
                for key, info in settings.VIDEO_MODELS.items()
                for slug in [MODEL_SLUGS.get(key, key)]
            ]
        return resp.json().get("models", [])
