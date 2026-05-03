"""Creative Video Studio — FastAPI server."""

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config as cfg
import database as db
from caption_generator import CaptionGenerator
from notion_manager import NotionManager
from video_assembler import VideoAssembler
from video_generator import VideoGenerator
from voiceover_generator import VoiceoverGenerator

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s — %(message)s")
log = logging.getLogger("studio")

# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(title="Creative Video Studio", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=str(cfg.UPLOADS_DIR)), name="uploads")
app.mount("/static", StaticFiles(directory=str(cfg.BASE_DIR / "static")), name="static")

# ── WebSocket broadcast ────────────────────────────────────────────────────────

_ws_clients: set[WebSocket] = set()


async def broadcast(event: str, data: dict):
    payload = json.dumps({"event": event, **data})
    dead = set()
    for ws in _ws_clients:
        try:
            await ws.send_text(payload)
        except Exception:
            dead.add(ws)
    _ws_clients.difference_update(dead)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _ws_clients.add(ws)
    try:
        while True:
            await ws.receive_text()  # keep-alive
    except WebSocketDisconnect:
        _ws_clients.discard(ws)


# ── Startup ────────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    db.init_db()
    log.info("Database initialised at %s", db.DB_PATH)


# ── Pydantic models ────────────────────────────────────────────────────────────

class SetupBody(BaseModel):
    notion_token: str
    parent_page_id: str


class ImportNotionBody(BaseModel):
    notion_token: str
    characters_db_id: str
    scenes_db_id: str
    project_name: str = "Imported Project"


class ProjectBody(BaseModel):
    name: str
    description: str = ""


class CharacterBody(BaseModel):
    project_id: str
    name: str
    voice_id: str = ""
    description: str = ""
    is_main_character: bool = False
    reference_image: str = ""


class SceneBody(BaseModel):
    project_id: str
    scene_number: int = 0
    title: str = ""
    script: str = ""
    scene_type: str = "Dialogue"
    model: str = ""
    duration: str = "10s"
    resolution: str = "720p"


class GenerateVideoBody(BaseModel):
    scene_id: str
    project_id: str
    prompt: str
    model: str = ""
    duration: str = "10s"
    resolution: str = "720p"
    use_previous_frame: bool = False
    generate_voiceover: bool = False
    generate_captions: bool = False
    assemble: bool = False


class GenerateAudioBody(BaseModel):
    scene_id: str
    project_id: str
    text: str
    voice_id: str


class SettingsBody(BaseModel):
    notion_api_key: str = ""
    higgsfield_api_id: str = ""
    higgsfield_api_secret: str = ""
    elevenlabs_api_key: str = ""


# ── Helper: resolve API keys (DB override > config default) ───────────────────

def _el_key()   -> str: return db.get_setting("elevenlabs_api_key")   or cfg.ELEVENLABS_API_KEY
def _hf_id()    -> str: return db.get_setting("higgsfield_api_id")    or cfg.HIGGSFIELD_API_ID
def _hf_sec()   -> str: return db.get_setting("higgsfield_api_secret") or cfg.HIGGSFIELD_API_SECRET
def _notion_key() -> str: return db.get_setting("notion_api_key")     or cfg.NOTION_API_KEY


# ── Routes: root ───────────────────────────────────────────────────────────────

@app.get("/")
async def serve_app():
    return FileResponse(str(cfg.BASE_DIR / "static" / "index.html"))


# ── Routes: status ─────────────────────────────────────────────────────────────

@app.get("/api/status")
async def api_status():
    vg = VideoGenerator(_hf_id(), _hf_sec())
    vo = VoiceoverGenerator(_el_key())
    notion_key = _notion_key()

    hf_status = await vg.test_connection()
    el_status  = await vo.test_connection()
    notion_ok  = False
    if notion_key:
        nm = NotionManager(notion_key)
        r  = await nm.test_connection()
        notion_ok = r.get("ok", False)

    return {
        "higgsfield": hf_status,
        "elevenlabs":  el_status,
        "notion":      {"ok": notion_ok, "configured": bool(notion_key)},
        "models":      cfg.HIGGSFIELD_MODELS,
    }


# ── Routes: settings ──────────────────────────────────────────────────────────

@app.get("/api/settings")
async def get_settings():
    return {
        "notion_api_key":        db.get_setting("notion_api_key", ""),
        "higgsfield_api_id":     db.get_setting("higgsfield_api_id", cfg.HIGGSFIELD_API_ID),
        "higgsfield_api_secret": db.get_setting("higgsfield_api_secret", cfg.HIGGSFIELD_API_SECRET),
        "elevenlabs_api_key":    db.get_setting("elevenlabs_api_key", cfg.ELEVENLABS_API_KEY),
    }


@app.post("/api/settings")
async def save_settings(body: SettingsBody):
    if body.notion_api_key:        db.set_setting("notion_api_key",        body.notion_api_key)
    if body.higgsfield_api_id:     db.set_setting("higgsfield_api_id",     body.higgsfield_api_id)
    if body.higgsfield_api_secret: db.set_setting("higgsfield_api_secret", body.higgsfield_api_secret)
    if body.elevenlabs_api_key:    db.set_setting("elevenlabs_api_key",    body.elevenlabs_api_key)
    return {"ok": True}


# ── Routes: Notion setup ───────────────────────────────────────────────────────

@app.post("/api/setup")
async def setup_notion(body: SetupBody):
    """Create Characters + Scenes databases under the given Notion page."""
    nm = NotionManager(body.notion_token)
    try:
        chars_db  = await nm.create_characters_database(body.parent_page_id)
        scenes_db = await nm.create_scenes_database(body.parent_page_id)
    except Exception as e:
        raise HTTPException(400, detail=str(e))

    # Store token
    db.set_setting("notion_api_key", body.notion_token)

    # Create a project record
    project_id = db.new_id()
    db.insert("projects", {
        "id":                    project_id,
        "name":                  "My Video Project",
        "description":           "Auto-created by Notion setup",
        "notion_characters_db":  chars_db["id"],
        "notion_scenes_db":      scenes_db["id"],
        "notion_page_id":        body.parent_page_id,
        "created_at":            db.now(),
        "updated_at":            db.now(),
    })

    return {
        "ok":           True,
        "project_id":   project_id,
        "characters_db": chars_db["id"],
        "scenes_db":    scenes_db["id"],
    }


@app.post("/api/import-notion")
async def import_notion(body: ImportNotionBody):
    """Link existing Notion databases to a new project and import data."""
    nm = NotionManager(body.notion_token)
    db.set_setting("notion_api_key", body.notion_token)

    project_id = db.new_id()
    db.insert("projects", {
        "id":                   project_id,
        "name":                 body.project_name,
        "description":          "Imported from Notion",
        "notion_characters_db": body.characters_db_id,
        "notion_scenes_db":     body.scenes_db_id,
        "notion_page_id":       "",
        "created_at":           db.now(),
        "updated_at":           db.now(),
    })

    # Import characters
    char_pages = await nm.query_database(body.characters_db_id)
    for page in char_pages:
        parsed = nm.parse_character(page)
        db.insert("characters", {
            "id":               db.new_id(),
            "project_id":       project_id,
            "name":             parsed["name"],
            "voice_id":         parsed["voice_id"],
            "description":      parsed["description"],
            "is_main_character": int(parsed["is_main_character"]),
            "notion_page_id":   parsed["notion_id"],
            "created_at":       db.now(),
            "updated_at":       db.now(),
            "reference_image":  "",
        })

    # Import scenes
    scene_pages = await nm.query_database(body.scenes_db_id)
    for page in scene_pages:
        parsed = nm.parse_scene(page)
        db.insert("scenes", {
            "id":           db.new_id(),
            "project_id":   project_id,
            "scene_number": parsed["scene_number"],
            "title":        parsed["title"],
            "script":       parsed["script"],
            "scene_type":   parsed["scene_type"],
            "model":        parsed["model"],
            "duration":     parsed["duration"],
            "resolution":   "720p",
            "characters":   "[]",
            "status":       parsed["status"],
            "notion_page_id": parsed["notion_id"],
            "video_url":    "",
            "thumbnail_url": "",
            "created_at":   db.now(),
            "updated_at":   db.now(),
        })

    return {"ok": True, "project_id": project_id}


# ── Routes: projects ───────────────────────────────────────────────────────────

@app.get("/api/projects")
async def list_projects():
    projects = db.select_all("projects")
    for p in projects:
        p["character_count"] = len(db.select_all("characters", "project_id = ?", [p["id"]]))
        p["scene_count"]     = len(db.select_all("scenes", "project_id = ?", [p["id"]]))
    return projects


@app.post("/api/projects")
async def create_project(body: ProjectBody):
    pid = db.new_id()
    db.insert("projects", {
        "id":                   pid,
        "name":                 body.name,
        "description":          body.description,
        "notion_characters_db": "",
        "notion_scenes_db":     "",
        "notion_page_id":       "",
        "created_at":           db.now(),
        "updated_at":           db.now(),
    })
    return db.select_one("projects", "id = ?", [pid])


@app.get("/api/projects/{project_id}")
async def get_project(project_id: str):
    p = db.select_one("projects", "id = ?", [project_id])
    if not p:
        raise HTTPException(404, "Project not found")
    p["characters"] = db.select_all("characters", "project_id = ?", [project_id])
    p["scenes"]     = db.select_all("scenes",     "project_id = ? ORDER BY scene_number", [project_id])
    return p


@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: str):
    db.delete("projects", "id = ?", [project_id])
    return {"ok": True}


# ── Routes: characters ─────────────────────────────────────────────────────────

@app.get("/api/characters")
async def list_characters(project_id: str = ""):
    if project_id:
        chars = db.select_all("characters", "project_id = ?", [project_id])
    else:
        chars = db.select_all("characters")
    return chars


@app.post("/api/characters")
async def create_character(body: CharacterBody):
    # Also push to Notion if project has a characters DB
    project = db.select_one("projects", "id = ?", [body.project_id])
    notion_id = ""
    if project and project.get("notion_characters_db") and _notion_key():
        nm = NotionManager(_notion_key())
        try:
            page = await nm.create_character_page(
                project["notion_characters_db"],
                body.dict(),
            )
            notion_id = page["id"]
        except Exception as e:
            log.warning("Could not push character to Notion: %s", e)

    cid = db.new_id()
    db.insert("characters", {
        "id":               cid,
        "project_id":       body.project_id,
        "name":             body.name,
        "voice_id":         body.voice_id,
        "description":      body.description,
        "is_main_character": int(body.is_main_character),
        "reference_image":  body.reference_image,
        "notion_page_id":   notion_id,
        "created_at":       db.now(),
        "updated_at":       db.now(),
    })
    return db.select_one("characters", "id = ?", [cid])


@app.delete("/api/characters/{char_id}")
async def delete_character(char_id: str):
    db.delete("characters", "id = ?", [char_id])
    return {"ok": True}


# ── Routes: scenes ─────────────────────────────────────────────────────────────

@app.get("/api/scenes")
async def list_scenes(project_id: str = ""):
    if project_id:
        scenes = db.select_all("scenes", "project_id = ? ORDER BY scene_number", [project_id])
    else:
        scenes = db.select_all("scenes")
    return scenes


@app.post("/api/scenes")
async def create_scene(body: SceneBody):
    model = body.model or VideoGenerator.suggest_model(body.scene_type)

    # Push to Notion if project has a scenes DB
    project = db.select_one("projects", "id = ?", [body.project_id])
    notion_id = ""
    if project and project.get("notion_scenes_db") and _notion_key():
        nm = NotionManager(_notion_key())
        try:
            page = await nm.create_scene_page(
                project["notion_scenes_db"],
                {**body.dict(), "model": model},
            )
            notion_id = page["id"]
        except Exception as e:
            log.warning("Could not push scene to Notion: %s", e)

    sid = db.new_id()
    db.insert("scenes", {
        "id":           sid,
        "project_id":   body.project_id,
        "scene_number": body.scene_number,
        "title":        body.title,
        "script":       body.script,
        "scene_type":   body.scene_type,
        "model":        model,
        "duration":     body.duration,
        "resolution":   body.resolution,
        "characters":   "[]",
        "status":       "Draft",
        "notion_page_id": notion_id,
        "video_url":    "",
        "thumbnail_url": "",
        "created_at":   db.now(),
        "updated_at":   db.now(),
    })
    return db.select_one("scenes", "id = ?", [sid])


@app.put("/api/scenes/{scene_id}")
async def update_scene(scene_id: str, body: dict):
    scene = db.select_one("scenes", "id = ?", [scene_id])
    if not scene:
        raise HTTPException(404, "Scene not found")
    allowed = {"title", "script", "scene_type", "model", "duration", "resolution", "status"}
    data = {k: v for k, v in body.items() if k in allowed}
    data["updated_at"] = db.now()
    db.update("scenes", data, "id = ?", [scene_id])
    return db.select_one("scenes", "id = ?", [scene_id])


@app.delete("/api/scenes/{scene_id}")
async def delete_scene(scene_id: str):
    db.delete("scenes", "id = ?", [scene_id])
    return {"ok": True}


# ── Routes: voices ─────────────────────────────────────────────────────────────

@app.get("/api/voices")
async def list_voices():
    vo = VoiceoverGenerator(_el_key())
    try:
        return await vo.list_voices()
    except Exception as e:
        raise HTTPException(502, detail=f"ElevenLabs error: {e}")


# ── Routes: video generation ───────────────────────────────────────────────────

@app.post("/api/generate-video")
async def start_video_generation(body: GenerateVideoBody, bg: BackgroundTasks):
    scene = db.select_one("scenes", "id = ?", [body.scene_id])
    if not scene:
        raise HTTPException(404, "Scene not found")

    model = body.model or VideoGenerator.suggest_model(scene.get("scene_type", "Dialogue"))

    # Optional: get last scene's video URL as reference frame
    ref_url = ""
    if body.use_previous_frame:
        prev = db.select_all(
            "scenes",
            "project_id = ? AND scene_number < ? ORDER BY scene_number DESC LIMIT 1",
            [body.project_id, scene.get("scene_number", 0)],
        )
        if prev and prev[0].get("video_url"):
            ref_url = prev[0]["video_url"]

    job_id = db.new_id()
    db.insert("video_jobs", {
        "id":                  job_id,
        "project_id":          body.project_id,
        "scene_id":            body.scene_id,
        "higgsfield_job_id":   "",
        "status":              "queued",
        "prompt":              body.prompt,
        "model":               model,
        "duration":            body.duration,
        "resolution":          body.resolution,
        "video_url":           "",
        "local_path":          "",
        "error_message":       "",
        "reference_image_url": ref_url,
        "created_at":          db.now(),
        "updated_at":          db.now(),
    })

    bg.add_task(
        _run_video_generation,
        job_id, body, model, ref_url, scene,
    )
    return {"job_id": job_id, "status": "queued"}


async def _run_video_generation(
    job_id: str,
    body: GenerateVideoBody,
    model: str,
    ref_url: str,
    scene: dict,
):
    def _upd(status: str, **extra):
        db.update("video_jobs", {"status": status, "updated_at": db.now(), **extra}, "id = ?", [job_id])

    await broadcast("job_update", {"job_id": job_id, "status": "generating"})
    _upd("generating")

    vg = VideoGenerator(_hf_id(), _hf_sec())
    try:
        result = await vg.generate_video(
            prompt=body.prompt,
            model=model,
            duration=body.duration,
            resolution=body.resolution,
            reference_image_url=ref_url,
        )
        hf_job = result["job_id"]
        _upd("polling", higgsfield_job_id=hf_job)

        final = await vg.wait_for_completion(hf_job)
        video_url = final.get("video_url", "")
        _upd("completed", video_url=video_url)

        # Update scene record
        db.update("scenes", {"video_url": video_url, "status": "Generated", "updated_at": db.now()}, "id = ?", [body.scene_id])

        # Update Notion if applicable
        if scene.get("notion_page_id") and _notion_key():
            nm = NotionManager(_notion_key())
            try:
                await nm.update_scene_status(scene["notion_page_id"], "Generated")
            except Exception:
                pass

        # Optional assembly
        if body.assemble and video_url:
            await _assemble_scene(job_id, body, scene, video_url)

        await broadcast("job_update", {"job_id": job_id, "status": "completed", "video_url": video_url})

    except Exception as e:
        log.error("Video generation failed: %s", e)
        _upd("failed", error_message=str(e)[:500])
        await broadcast("job_update", {"job_id": job_id, "status": "failed", "error": str(e)})


async def _assemble_scene(job_id: str, body: GenerateVideoBody, scene: dict, video_url: str):
    assembler = VideoAssembler()
    audio_path, srt_path = "", ""

    if body.generate_voiceover and scene.get("script"):
        vo = VoiceoverGenerator(_el_key())
        chars = db.select_all("characters", "project_id = ?", [body.project_id])
        voice_map = {c["name"]: c["voice_id"] for c in chars if c.get("voice_id")}
        try:
            segments = await vo.generate_scene_voiceover(scene["script"], voice_map, body.scene_id)
            paths = [s["audio_file"] for s in segments if s.get("audio_file")]
            if paths:
                audio_path = await vo.combine_audio_segments(paths, f"{body.scene_id}_vo.mp3")
        except Exception as e:
            log.warning("Voiceover generation failed: %s", e)

    if body.generate_captions and scene.get("script"):
        cg = CaptionGenerator()
        dur_s = int(body.duration.replace("s", ""))
        srt_path = cg.generate_srt(scene["script"], dur_s, f"{body.scene_id}.srt")

    try:
        final_path = await assembler.assemble(
            video_url, audio_path, srt_path,
            f"scene_{body.scene_id}_final.mp4", body.resolution,
        )
        db.update("video_jobs", {"local_path": final_path, "updated_at": db.now()}, "id = ?", [job_id])
    except Exception as e:
        log.warning("Assembly failed: %s", e)


@app.get("/api/generate-video/{job_id}")
async def get_video_job(job_id: str):
    job = db.select_one("video_jobs", "id = ?", [job_id])
    if not job:
        raise HTTPException(404, "Job not found")
    # If still polling, check Higgsfield directly
    if job["status"] == "polling" and job.get("higgsfield_job_id"):
        try:
            vg = VideoGenerator(_hf_id(), _hf_sec())
            remote = await vg.get_status(job["higgsfield_job_id"])
            if remote["status"].lower() in ("completed", "done", "success"):
                db.update("video_jobs", {
                    "status":    "completed",
                    "video_url": remote.get("video_url", ""),
                    "updated_at": db.now(),
                }, "id = ?", [job_id])
                job = db.select_one("video_jobs", "id = ?", [job_id])
        except Exception:
            pass
    return job


@app.get("/api/video-jobs")
async def list_video_jobs(project_id: str = "", scene_id: str = ""):
    where, params = [], []
    if project_id:
        where.append("project_id = ?"); params.append(project_id)
    if scene_id:
        where.append("scene_id = ?"); params.append(scene_id)
    clause = " AND ".join(where) if where else ""
    jobs = db.select_all("video_jobs", clause + " ORDER BY created_at DESC", params)
    return jobs


# ── Routes: audio generation ───────────────────────────────────────────────────

@app.post("/api/generate-audio")
async def start_audio_generation(body: GenerateAudioBody, bg: BackgroundTasks):
    job_id = db.new_id()
    db.insert("audio_jobs", {
        "id":           job_id,
        "project_id":   body.project_id,
        "scene_id":     body.scene_id,
        "text_content": body.text,
        "voice_id":     body.voice_id,
        "voice_name":   "",
        "status":       "queued",
        "audio_file":   "",
        "error_message": "",
        "created_at":   db.now(),
        "updated_at":   db.now(),
    })
    bg.add_task(_run_audio_generation, job_id, body)
    return {"job_id": job_id, "status": "queued"}


async def _run_audio_generation(job_id: str, body: GenerateAudioBody):
    def _upd(status: str, **extra):
        db.update("audio_jobs", {"status": status, "updated_at": db.now(), **extra}, "id = ?", [job_id])

    _upd("generating")
    await broadcast("job_update", {"job_id": job_id, "status": "generating", "type": "audio"})
    vo = VoiceoverGenerator(_el_key())
    try:
        path = await vo.generate_audio(body.text, body.voice_id, f"{job_id}.mp3")
        _upd("completed", audio_file=path)
        rel_path = "/uploads/audio/" + Path(path).name
        await broadcast("job_update", {"job_id": job_id, "status": "completed", "audio_url": rel_path, "type": "audio"})
    except Exception as e:
        log.error("Audio generation failed: %s", e)
        _upd("failed", error_message=str(e)[:500])
        await broadcast("job_update", {"job_id": job_id, "status": "failed", "error": str(e), "type": "audio"})


@app.get("/api/audio-jobs")
async def list_audio_jobs(project_id: str = ""):
    jobs = db.select_all(
        "audio_jobs",
        ("project_id = ? ORDER BY created_at DESC" if project_id else "ORDER BY created_at DESC"),
        ([project_id] if project_id else []),
    )
    for j in jobs:
        if j.get("audio_file"):
            j["audio_url"] = "/uploads/audio/" + Path(j["audio_file"]).name
    return jobs


# ── Routes: download ───────────────────────────────────────────────────────────

@app.get("/api/download/{video_id}")
async def download_video(video_id: str):
    job = db.select_one("video_jobs", "id = ?", [video_id])
    if not job:
        raise HTTPException(404, "Job not found")

    local = job.get("local_path")
    if local and Path(local).exists():
        return FileResponse(local, media_type="video/mp4", filename=f"scene_{video_id}.mp4")

    remote = job.get("video_url")
    if remote:
        return {"redirect": remote}

    raise HTTPException(404, "Video file not available yet")


# ── Routes: models / config ────────────────────────────────────────────────────

@app.get("/api/models")
async def list_models():
    return {
        "models":      cfg.HIGGSFIELD_MODELS,
        "scene_types": cfg.SCENE_TYPES,
        "durations":   cfg.VIDEO_DURATIONS,
        "resolutions": cfg.VIDEO_RESOLUTIONS,
        "suggestion_map": cfg.SCENE_TYPE_MODEL_MAP,
    }


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=cfg.SERVER_HOST, port=cfg.SERVER_PORT, reload=True)
