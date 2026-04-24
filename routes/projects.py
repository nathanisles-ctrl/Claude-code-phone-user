from fastapi import APIRouter, HTTPException
from models.schemas import ProjectCreate, ProjectUpdate, ProjectResponse
import database as db

router = APIRouter(prefix="/api/projects", tags=["Projects"])


@router.get("", response_model=list[ProjectResponse])
async def list_projects():
    return db.list_projects()


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(body: ProjectCreate):
    return db.create_project(
        name=body.name,
        description=body.description,
        notion_workspace_id=body.notion_workspace_id,
    )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: int):
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(project_id: int, body: ProjectUpdate):
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    updates = body.model_dump(exclude_none=True)
    if not updates:
        return project
    return db.update_project(project_id, **updates)


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: int):
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    db.delete_project(project_id)
