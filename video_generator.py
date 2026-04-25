import asyncio
import logging
import time
from pathlib import Path
from typing import Optional
import httpx
from config import settings

logger = logging.getLogger(__name__)

HIGGSFIELD_BASE = "https://platform.higgsfield.ai"

# Auth header: "Key {api_id}:{api_secret}"
def _auth_headers() -> dict:
    return {
        "Authorization": f"Key {settings.HIGGSFIELD_API_ID}:{settings.HIGGSFIELD_API_SECRET}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

# Higgsfield model IDs — format: provider/model/variant
MODEL_IDS = {
    "veo3":       "google/veo-3/standard",
    "seedance2":  "bytedance/seedance-1-lite/standard",
    "kling3":     "kuaishou/kling-1-6-pro/standard",
    "sora2":      "openai/sora/standard",
    "higgsfield": "higgsfield-ai/soul/standard",
    "auto":       "higgsfield-ai/soul/standard",
}

ASPECT_RATIO = "16:9"


def _resolve_model(model: str) -> str:
    """Return the Higgsfield model_id for a given key."""
    return MODEL_IDS.get(model, MODEL_IDS["higgsfield"])


async def start_generation(
    prompt: str,
    model: str = "auto",
    duration: int = 5,
    resolution: str = "720p",
    reference_image_urls: Optional[list[str]] = None,
) -> dict:
    """Submit a generation request. Returns the queued response with request_id."""
    model_id = _resolve_model(model)

    # Higgsfield only supports 480p, 720p, 1080p
    if resolution == "4k":
        resolution = "1080p"

    payload: dict = {
        "prompt": prompt,
        "aspect_ratio": ASPECT_RATIO,
        "resolution": resolution,
        "duration": duration,
    }
    if reference_image_urls:
        payload["reference_images"] = reference_image_urls

    url = f"{HIGGSFIELD_BASE}/{model_id}"
    logger.info("Submitting to Higgsfield: %s | prompt='%.80s'", url, prompt)

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, headers=_auth_headers(), json=payload)
        if resp.status_code == 401:
            raise ValueError("Higgsfield authentication failed — check API ID and Secret")
        if resp.status_code == 404:
            raise ValueError(f"Model not found: {model_id}. Check model ID at higgsfield.ai")
        resp.raise_for_status()
        data = resp.json()
        logger.info("Generation queued: request_id=%s", data.get("request_id"))
        return data


async def get_status(request_id: str) -> dict:
    """Poll the status of a generation request."""
    url = f"{HIGGSFIELD_BASE}/requests/{request_id}/status"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=_auth_headers())
        resp.raise_for_status()
        return resp.json()


async def cancel_request(request_id: str) -> bool:
    """Cancel a queued request. Only works while status is 'queued'."""
    url = f"{HIGGSFIELD_BASE}/requests/{request_id}/cancel"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, headers=_auth_headers())
        return resp.status_code == 202


async def wait_for_completion(
    request_id: str,
    timeout_seconds: int = 600,
    poll_interval: int = 10,
    progress_callback=None,
) -> dict:
    """
    Poll until the request completes, fails, or times out.
    Returns the final status dict containing video.url on success.
    """
    deadline = time.time() + timeout_seconds
    attempt = 0

    while time.time() < deadline:
        await asyncio.sleep(poll_interval)
        attempt += 1
        try:
            status = await get_status(request_id)
        except httpx.HTTPError as exc:
            logger.warning("Poll attempt %d failed: %s", attempt, exc)
            continue

        state = status.get("status", "").lower()
        logger.debug("Request %s: %s (attempt %d)", request_id, state, attempt)

        if progress_callback:
            await progress_callback(state, attempt)

        if state == "completed":
            return status
        if state == "failed":
            raise RuntimeError(f"Higgsfield generation failed (request_id={request_id})")
        if state == "nsfw":
            raise ValueError("Content failed Higgsfield moderation — revise your prompt")

    raise TimeoutError(f"Generation timed out after {timeout_seconds}s (request_id={request_id})")


async def download_video(video_url: str, output_path: Path) -> Path:
    """Download the finished MP4 to output_path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading video → %s", output_path)
    async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
        async with client.stream("GET", video_url) as resp:
            resp.raise_for_status()
            with open(output_path, "wb") as f:
                async for chunk in resp.aiter_bytes(8192):
                    f.write(chunk)
    logger.info("Video saved: %.1f MB", output_path.stat().st_size / 1_000_000)
    return output_path


async def generate_video_full(
    prompt: str,
    output_path: Path,
    model: str = "auto",
    duration: int = 5,
    resolution: str = "720p",
    reference_image_urls: Optional[list[str]] = None,
    progress_callback=None,
) -> Path:
    """End-to-end: submit → poll → download. Returns local video path."""
    queued = await start_generation(
        prompt=prompt,
        model=model,
        duration=duration,
        resolution=resolution,
        reference_image_urls=reference_image_urls,
    )

    request_id = queued.get("request_id")
    if not request_id:
        raise ValueError(f"No request_id in Higgsfield response: {queued}")

    final = await wait_for_completion(
        request_id=request_id,
        progress_callback=progress_callback,
    )

    video_url = (final.get("video") or {}).get("url")
    if not video_url:
        raise ValueError(f"No video URL in completed response: {final}")

    return await download_video(video_url, output_path)


def suggest_model(scene_type: str) -> str:
    key = settings.SCENE_TYPE_TO_MODEL.get(scene_type, "higgsfield")
    return key


async def list_available_models() -> list[dict]:
    return [
        {"id": k, "model_id": v, "name": k.replace("_", " ").title()}
        for k, v in MODEL_IDS.items()
        if k != "auto"
    ]
