from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.repository import Repository
from app.models.session import Session, Conversation
from app.models.session import SessionStatus
from app.schemas.session import SessionCreate, SessionUpdate, SessionResponse, ConversationCreate, ConversationUpdate, ConversationResponse
from app.services.session_snapshot import capture_git_snapshot

router = APIRouter()


@router.post("/{repo_id}/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(repo_id: str, payload: SessionCreate, db: AsyncSession = Depends(get_db)):
    repository = await db.get(Repository, repo_id)
    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")
    snapshot = capture_git_snapshot(repository.local_path)
    session = Session(
        repository_id=repo_id,
        starting_branch=snapshot["branch"],
        starting_commit_sha=snapshot["commit_sha"],
        starting_working_tree_dirty=snapshot["working_tree_dirty"],
        git_snapshot_status=snapshot["status"],
        **payload.model_dump(exclude={"repository_id"}),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.get("/{repo_id}/sessions")
async def list_sessions(repo_id: str, skip: int = 0, limit: int = 50, db: AsyncSession = Depends(get_db)):
    if not await db.get(Repository, repo_id):
        raise HTTPException(status_code=404, detail="Repository not found")
    limit = min(max(limit, 1), 200)
    total = await db.scalar(select(func.count()).select_from(Session).where(Session.repository_id == repo_id)) or 0
    rows = await db.scalars(select(Session).where(Session.repository_id == repo_id).order_by(Session.updated_at.desc()).offset(max(skip, 0)).limit(limit))
    return {"items": rows.all(), "total": total}


@router.get("/{repo_id}/sessions/{session_id}", response_model=SessionResponse)
async def get_session(repo_id: str, session_id: str, db: AsyncSession = Depends(get_db)):
    row = await db.get(Session, session_id)
    if not row or row.repository_id != repo_id:
        raise HTTPException(status_code=404, detail="Session not found")
    return row


@router.patch("/{repo_id}/sessions/{session_id}", response_model=SessionResponse)
async def update_session(repo_id: str, session_id: str, payload: SessionUpdate, db: AsyncSession = Depends(get_db)):
    row = await db.get(Session, session_id)
    if not row or row.repository_id != repo_id:
        raise HTTPException(status_code=404, detail="Session not found")
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(row, key, value)
    if row.status == SessionStatus.COMPLETED:
        repository = await db.get(Repository, repo_id)
        if repository:
            snapshot = capture_git_snapshot(repository.local_path)
            row.handoff_branch = snapshot["branch"]
            row.handoff_commit_sha = snapshot["commit_sha"]
            row.handoff_changed_files = snapshot["changed_files"]
            row.handoff_working_tree_dirty = snapshot["working_tree_dirty"]
            row.git_snapshot_status = snapshot["status"]
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/{repo_id}/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(repo_id: str, session_id: str, db: AsyncSession = Depends(get_db)):
    row = await db.get(Session, session_id)
    if not row or row.repository_id != repo_id:
        raise HTTPException(status_code=404, detail="Session not found")
    await db.delete(row)
    await db.commit()
    return None


@router.post("/{repo_id}/sessions/{session_id}/conversations", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(repo_id: str, session_id: str, payload: ConversationCreate, db: AsyncSession = Depends(get_db)):
    session = await db.get(Session, session_id)
    if not session or session.repository_id != repo_id:
        raise HTTPException(status_code=404, detail="Session not found")
    conversation = Conversation(repository_id=repo_id, session_id=session_id, **payload.model_dump(exclude={"repository_id", "session_id"}))
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


@router.get("/{repo_id}/sessions/{session_id}/conversations")
async def list_conversations(repo_id: str, session_id: str, db: AsyncSession = Depends(get_db)):
    session = await db.get(Session, session_id)
    if not session or session.repository_id != repo_id:
        raise HTTPException(status_code=404, detail="Session not found")
    rows = await db.scalars(select(Conversation).where(Conversation.session_id == session_id).order_by(Conversation.created_at.desc()))
    items = rows.all()
    return {"items": items, "total": len(items)}


@router.patch("/{repo_id}/sessions/{session_id}/conversations/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(repo_id: str, session_id: str, conversation_id: str, payload: ConversationUpdate, db: AsyncSession = Depends(get_db)):
    row = await db.get(Conversation, conversation_id)
    if not row or row.repository_id != repo_id or row.session_id != session_id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.commit()
    await db.refresh(row)
    return row
