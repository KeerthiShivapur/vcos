"""Joy & Break Layer — Games API (Team Games & Collaborative Activities)."""

from datetime import datetime, timezone
from typing import Optional, List
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.schemas.common import Message

router = APIRouter(prefix="/games", tags=["Joy & Break Layer — Games"])


# =============================================================================
# Game Models
# =============================================================================

class GameType(str):
    TRIVIA = "trivia"
    PUZZLE = "puzzle"
    WORD_CHALLENGE = "word_challenge"
    COLLABORATIVE = "collaborative"


class GameStatus(str):
    WAITING = "waiting"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TriviaQuestion(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    question: str
    options: List[str] = Field(min_items=2, max_items=6)
    correct_answer: int = Field(ge=0)
    category: str
    difficulty: str = Field(pattern="^(easy|medium|hard)$")
    points: int = Field(default=10, ge=1)
    explanation: Optional[str] = None


class TriviaSessionCreate(BaseModel):
    game_type: str = Field(default=GameType.TRIVIA)
    title: str = Field(min_length=1, max_length=100)
    description: Optional[str] = None
    questions: List[TriviaQuestion] = Field(min_items=1)
    time_per_question: int = Field(default=30, ge=10, le=120)
    max_players: int = Field(default=20, ge=2, le=100)
    is_public: bool = True


class TriviaSessionOut(BaseModel):
    id: str
    organization_id: str
    game_type: str
    title: str
    description: Optional[str]
    questions: List[TriviaQuestion]
    time_per_question: int
    max_players: int
    is_public: bool
    status: str
    current_question: int
    created_by: str
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]

    class Config:
        from_attributes = True


class TriviaAnswer(BaseModel):
    question_index: int = Field(ge=0)
    answer: int = Field(ge=0)
    time_taken: int = Field(ge=0)


class TriviaAnswerOut(BaseModel):
    question_index: int
    answer: int
    is_correct: bool
    points_earned: int
    time_taken: int
    correct_answer: int
    explanation: Optional[str]


class TriviaPlayerState(BaseModel):
    player_id: str
    player_name: str
    score: int = 0
    correct_count: int = 0
    answers: List[TriviaAnswerOut] = []


class TriviaSessionState(BaseModel):
    session: TriviaSessionOut
    players: List[TriviaPlayerState]
    current_question: Optional[TriviaQuestion] = None
    time_remaining: int = 0
    is_host: bool = False
    can_join: bool = True


class PuzzleSessionCreate(BaseModel):
    game_type: str = Field(default=GameType.PUZZLE)
    title: str = Field(min_length=1, max_length=100)
    description: Optional[str] = None
    puzzle_data: dict  # Flexible puzzle definition
    max_players: int = Field(default=10, ge=1, le=50)
    time_limit: Optional[int] = Field(default=None, ge=60)
    is_public: bool = True


class PuzzleSessionOut(BaseModel):
    id: str
    organization_id: str
    game_type: str
    title: str
    description: Optional[str]
    puzzle_data: dict
    max_players: int
    time_limit: Optional[int]
    is_public: bool
    status: str
    progress: dict
    created_by: str
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]

    class Config:
        from_attributes = True


class PuzzleAction(BaseModel):
    action_type: str
    payload: dict


class GameListItem(BaseModel):
    id: str
    game_type: str
    title: str
    description: Optional[str]
    status: str
    player_count: int
    max_players: int
    created_by: str
    created_at: str
    is_public: bool


# =============================================================================
# In-Memory Game State (for demo - production would use Redis/DB)
# =============================================================================

GAME_SESSIONS: dict = {}


async def _get_employee_id(db: AsyncSession, org_id: str, user_id: str) -> Optional[str]:
    from app.models.employee import Employee
    result = await db.execute(
        select(Employee).where(Employee.organization_id == org_id, Employee.user_id == user_id)
    )
    emp = result.scalar_one_or_none()
    return emp.id if emp else None


def _generate_trivia_questions() -> List[TriviaQuestion]:
    """Generate sample trivia questions for demo."""
    return [
        TriviaQuestion(
            question="What is the capital of France?",
            options=["London", "Berlin", "Paris", "Madrid"],
            correct_answer=2,
            category="Geography",
            difficulty="easy",
            points=10,
            explanation="Paris has been the capital of France since 987 AD."
        ),
        TriviaQuestion(
            question="Which planet is known as the Red Planet?",
            options=["Venus", "Mars", "Jupiter", "Saturn"],
            correct_answer=1,
            category="Science",
            difficulty="easy",
            points=10,
            explanation="Mars appears red due to iron oxide on its surface."
        ),
        TriviaQuestion(
            question="What is the largest ocean on Earth?",
            options=["Atlantic", "Indian", "Arctic", "Pacific"],
            correct_answer=3,
            category="Geography",
            difficulty="easy",
            points=10,
            explanation="The Pacific Ocean covers about 63 million square miles."
        ),
        TriviaQuestion(
            question="Who wrote 'Romeo and Juliet'?",
            options=["Charles Dickens", "William Shakespeare", "Jane Austen", "Mark Twain"],
            correct_answer=1,
            category="Literature",
            difficulty="easy",
            points=10,
            explanation="Shakespeare wrote Romeo and Juliet around 1595."
        ),
        TriviaQuestion(
            question="What is the chemical symbol for gold?",
            options=["Go", "Gd", "Au", "Ag"],
            correct_answer=2,
            category="Science",
            difficulty="medium",
            points=15,
            explanation="Au comes from the Latin 'aurum' meaning gold."
        ),
    ]


def _generate_puzzle_data() -> dict:
    """Generate a sample collaborative puzzle."""
    return {
        "type": "word_puzzle",
        "grid_size": 5,
        "clues": {
            "across": {
                "1": "A place where people work together",
                "3": "Opposite of fail",
                "5": "To create something new"
            },
            "down": {
                "1": "Group of people with shared goal",
                "2": "To join forces",
                "4": "A task or piece of work"
            }
        },
        "solution": [
            ["O", "F", "F", "I", "C", "E"],
            ["S", "U", "C", "C", "E", "E"],
            ["I", "N", "N", "O", "V", "A"],
            ["T", "E", "A", "M", "W", "O"],
            ["U", "N", "I", "T", "E", "D"]
        ],
        "hints_enabled": True
    }


# =============================================================================
# Trivia Endpoints
# =============================================================================

@router.post("/trivia", response_model=TriviaSessionOut, status_code=201)
async def create_trivia_session(
    payload: TriviaSessionCreate,
    user: User = Depends(require_permission("communication:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Create a new trivia game session."""
    emp_id = await _get_employee_id(db, org.id, user.id)
    if not emp_id:
        raise HTTPException(400, "No employee profile linked")

    session_id = uuid4().hex
    session = {
        "id": session_id,
        "organization_id": org.id,
        "game_type": payload.game_type,
        "title": payload.title,
        "description": payload.description,
        "questions": [q.model_dump() for q in payload.questions] if payload.questions else [q.model_dump() for q in _generate_trivia_questions()],
        "time_per_question": payload.time_per_question,
        "max_players": payload.max_players,
        "is_public": payload.is_public,
        "status": GameStatus.WAITING,
        "current_question": 0,
        "created_by": emp_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "started_at": None,
        "completed_at": None,
        "players": {emp_id: {"player_id": emp_id, "player_name": user.full_name, "score": 0, "correct_count": 0, "answers": []}},
        "answers": {},
    }
    GAME_SESSIONS[session_id] = session
    return TriviaSessionOut(**session)


@router.get("/trivia", response_model=List[GameListItem])
async def list_trivia_sessions(
    status: Optional[str] = None,
    is_public: Optional[bool] = None,
    user: User = Depends(require_permission("communication:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """List trivia sessions for the organization."""
    sessions = []
    for s in GAME_SESSIONS.values():
        if s["organization_id"] != org.id:
            continue
        if status and s["status"] != status:
            continue
        if is_public is not None and s["is_public"] != is_public:
            continue
        sessions.append(GameListItem(
            id=s["id"],
            game_type=s["game_type"],
            title=s["title"],
            description=s.get("description"),
            status=s["status"],
            player_count=len(s.get("players", {})),
            max_players=s["max_players"],
            created_by=s["created_by"],
            created_at=s["created_at"],
            is_public=s["is_public"],
        ))
    return sessions


@router.get("/trivia/{session_id}", response_model=TriviaSessionState)
async def get_trivia_session(
    session_id: str,
    user: User = Depends(require_permission("communication:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Get trivia session state for a player."""
    emp_id = await _get_employee_id(db, org.id, user.id)
    if not emp_id:
        raise HTTPException(400, "No employee profile linked")

    session = GAME_SESSIONS.get(session_id)
    if not session or session["organization_id"] != org.id:
        raise HTTPException(404, "Session not found")

    is_host = session["created_by"] == emp_id
    is_player = emp_id in session.get("players", {})
    can_join = session["status"] == GameStatus.WAITING and len(session.get("players", {})) < session["max_players"]

    # Build player states
    players = []
    for pid, pdata in session.get("players", {}).items():
        players.append(TriviaPlayerState(**pdata))

    current_q = None
    if session["status"] == GameStatus.ACTIVE and session["current_question"] < len(session["questions"]):
        q = session["questions"][session["current_question"]]
        # Don't reveal correct answer to players
        current_q = TriviaQuestion(
            id=q["id"],
            question=q["question"],
            options=q["options"],
            correct_answer=-1,  # Hidden
            category=q["category"],
            difficulty=q["difficulty"],
            points=q["points"],
            explanation=None
        )

    return TriviaSessionState(
        session=TriviaSessionOut(**session),
        players=players,
        current_question=current_q,
        time_remaining=session["time_per_question"] if session["status"] == GameStatus.ACTIVE else 0,
        is_host=is_host,
        can_join=can_join and not is_player,
    )


@router.post("/trivia/{session_id}/join", response_model=TriviaSessionState)
async def join_trivia_session(
    session_id: str,
    user: User = Depends(require_permission("communication:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Join a trivia session."""
    emp_id = await _get_employee_id(db, org.id, user.id)
    if not emp_id:
        raise HTTPException(400, "No employee profile linked")

    session = GAME_SESSIONS.get(session_id)
    if not session or session["organization_id"] != org.id:
        raise HTTPException(404, "Session not found")

    if session["status"] != GameStatus.WAITING:
        raise HTTPException(400, "Session is not accepting players")

    if len(session.get("players", {})) >= session["max_players"]:
        raise HTTPException(400, "Session is full")

    if emp_id not in session.get("players", {}):
        session["players"][emp_id] = {
            "player_id": emp_id,
            "player_name": user.full_name,
            "score": 0,
            "correct_count": 0,
            "answers": []
        }

    return await get_trivia_session(session_id, user, org, db)


@router.post("/trivia/{session_id}/start", response_model=TriviaSessionState)
async def start_trivia_session(
    session_id: str,
    user: User = Depends(require_permission("communication:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Start the trivia game (host only)."""
    emp_id = await _get_employee_id(db, org.id, user.id)
    if not emp_id:
        raise HTTPException(400, "No employee profile linked")

    session = GAME_SESSIONS.get(session_id)
    if not session or session["organization_id"] != org.id:
        raise HTTPException(404, "Session not found")

    if session["created_by"] != emp_id:
        raise HTTPException(403, "Only the host can start the game")

    if len(session.get("players", {})) < 2:
        raise HTTPException(400, "Need at least 2 players to start")

    session["status"] = GameStatus.ACTIVE
    session["current_question"] = 0
    session["started_at"] = datetime.now(timezone.utc).isoformat()

    return await get_trivia_session(session_id, user, org, db)


@router.post("/trivia/{session_id}/answer", response_model=TriviaAnswerOut)
async def submit_trivia_answer(
    session_id: str,
    payload: TriviaAnswer,
    user: User = Depends(require_permission("communication:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Submit an answer to the current question."""
    emp_id = await _get_employee_id(db, org.id, user.id)
    if not emp_id:
        raise HTTPException(400, "No employee profile linked")

    session = GAME_SESSIONS.get(session_id)
    if not session or session["organization_id"] != org.id:
        raise HTTPException(404, "Session not found")

    if session["status"] != GameStatus.ACTIVE:
        raise HTTPException(400, "Game is not active")

    if emp_id not in session.get("players", {}):
        raise HTTPException(403, "You are not a player in this session")

    if payload.question_index != session["current_question"]:
        raise HTTPException(400, "Invalid question index")

    question = session["questions"][payload.question_index]
    is_correct = payload.answer == question["correct_answer"]
    points = question["points"] if is_correct else 0

    answer_out = TriviaAnswerOut(
        question_index=payload.question_index,
        answer=payload.answer,
        is_correct=is_correct,
        points_earned=points,
        time_taken=payload.time_taken,
        correct_answer=question["correct_answer"],
        explanation=question.get("explanation")
    )

    # Update player state
    player = session["players"][emp_id]
    player["answers"].append(answer_out.model_dump())
    if is_correct:
        player["score"] += points
        player["correct_count"] += 1

    return answer_out


@router.post("/trivia/{session_id}/next", response_model=TriviaSessionState)
async def next_trivia_question(
    session_id: str,
    user: User = Depends(require_permission("communication:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Advance to next question (host only)."""
    emp_id = await _get_employee_id(db, org.id, user.id)
    if not emp_id:
        raise HTTPException(400, "No employee profile linked")

    session = GAME_SESSIONS.get(session_id)
    if not session or session["organization_id"] != org.id:
        raise HTTPException(404, "Session not found")

    if session["created_by"] != emp_id:
        raise HTTPException(403, "Only the host can advance questions")

    session["current_question"] += 1
    if session["current_question"] >= len(session["questions"]):
        session["status"] = GameStatus.COMPLETED
        session["completed_at"] = datetime.now(timezone.utc).isoformat()

    return await get_trivia_session(session_id, user, org, db)


# =============================================================================
# Puzzle Endpoints
# =============================================================================

@router.post("/puzzle", response_model=PuzzleSessionOut, status_code=201)
async def create_puzzle_session(
    payload: PuzzleSessionCreate,
    user: User = Depends(require_permission("communication:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Create a collaborative puzzle session."""
    emp_id = await _get_employee_id(db, org.id, user.id)
    if not emp_id:
        raise HTTPException(400, "No employee profile linked")

    session_id = uuid4().hex
    puzzle_data = payload.puzzle_data or _generate_puzzle_data()

    session = {
        "id": session_id,
        "organization_id": org.id,
        "game_type": payload.game_type,
        "title": payload.title,
        "description": payload.description,
        "puzzle_data": puzzle_data,
        "max_players": payload.max_players,
        "time_limit": payload.time_limit,
        "is_public": payload.is_public,
        "status": GameStatus.WAITING,
        "progress": {"completed_cells": 0, "total_cells": 25},
        "created_by": emp_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "started_at": None,
        "completed_at": None,
        "players": {emp_id: {"player_id": emp_id, "player_name": user.full_name}},
    }
    GAME_SESSIONS[session_id] = session
    return PuzzleSessionOut(**session)


@router.get("/puzzle", response_model=List[GameListItem])
async def list_puzzle_sessions(
    status: Optional[str] = None,
    is_public: Optional[bool] = None,
    user: User = Depends(require_permission("communication:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """List puzzle sessions."""
    sessions = []
    for s in GAME_SESSIONS.values():
        if s["organization_id"] != org.id:
            continue
        if s["game_type"] != GameType.PUZZLE:
            continue
        if status and s["status"] != status:
            continue
        if is_public is not None and s["is_public"] != is_public:
            continue
        sessions.append(GameListItem(
            id=s["id"],
            game_type=s["game_type"],
            title=s["title"],
            description=s.get("description"),
            status=s["status"],
            player_count=len(s.get("players", {})),
            max_players=s["max_players"],
            created_by=s["created_by"],
            created_at=s["created_at"],
            is_public=s["is_public"],
        ))
    return sessions


@router.get("/puzzle/{session_id}", response_model=PuzzleSessionOut)
async def get_puzzle_session(
    session_id: str,
    user: User = Depends(require_permission("communication:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Get puzzle session state."""
    emp_id = await _get_employee_id(db, org.id, user.id)
    if not emp_id:
        raise HTTPException(400, "No employee profile linked")

    session = GAME_SESSIONS.get(session_id)
    if not session or session["organization_id"] != org.id:
        raise HTTPException(404, "Session not found")

    return PuzzleSessionOut(**session)


@router.post("/puzzle/{session_id}/action", response_model=PuzzleSessionOut)
async def puzzle_action(
    session_id: str,
    payload: PuzzleAction,
    user: User = Depends(require_permission("communication:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Submit a puzzle action (collaborative)."""
    emp_id = await _get_employee_id(db, org.id, user.id)
    if not emp_id:
        raise HTTPException(400, "No employee profile linked")

    session = GAME_SESSIONS.get(session_id)
    if not session or session["organization_id"] != org.id:
        raise HTTPException(404, "Session not found")

    if session["status"] != GameStatus.ACTIVE and session["status"] != GameStatus.WAITING:
        if session["status"] == GameStatus.WAITING:
            if len(session.get("players", {})) >= 1:
                session["status"] = GameStatus.ACTIVE
                session["started_at"] = datetime.now(timezone.utc).isoformat()
            else:
                raise HTTPException(400, "Need at least 1 player")
        else:
            raise HTTPException(400, "Puzzle is not active")

    # Simple progress tracking
    if payload.action_type == "fill_cell":
        session["progress"]["completed_cells"] = min(
            session["progress"].get("completed_cells", 0) + 1,
            session["progress"].get("total_cells", 25)
        )
        if session["progress"]["completed_cells"] >= session["progress"]["total_cells"]:
            session["status"] = GameStatus.COMPLETED
            session["completed_at"] = datetime.now(timezone.utc).isoformat()

    return PuzzleSessionOut(**session)


# =============================================================================
# Game Catalog / Discovery
# =============================================================================

@router.get("/catalog", response_model=List[dict])
async def game_catalog(
    user: User = Depends(require_permission("communication:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Get available game types and templates."""
    return [
        {
            "game_type": GameType.TRIVIA,
            "title": "Quick Trivia",
            "description": "Fast-paced multiplayer trivia with categories and difficulty levels",
            "min_players": 2,
            "max_players": 20,
            "estimated_duration": "5-15 minutes",
            "tags": ["competitive", "knowledge", "quick"],
            "icon": "🧠"
        },
        {
            "game_type": GameType.PUZZLE,
            "title": "Collaborative Crossword",
            "description": "Work together to solve a crossword puzzle",
            "min_players": 1,
            "max_players": 10,
            "estimated_duration": "10-30 minutes",
            "tags": ["collaborative", "word", "teamwork"],
            "icon": "🧩"
        },
        {
            "game_type": GameType.WORD_CHALLENGE,
            "title": "Word Race",
            "description": "Form as many words as possible from given letters",
            "min_players": 2,
            "max_players": 8,
            "estimated_duration": "3-5 minutes",
            "tags": ["competitive", "word", "quick"],
            "icon": "📝"
        },
        {
            "game_type": GameType.COLLABORATIVE,
            "title": "Team Escape Room",
            "description": "Solve riddles together to escape before time runs out",
            "min_players": 3,
            "max_players": 8,
            "estimated_duration": "15-30 minutes",
            "tags": ["collaborative", "puzzle", "teamwork"],
            "icon": "🔓"
        },
    ]


@router.get("/sessions", response_model=List[GameListItem])
async def list_all_sessions(
    game_type: Optional[str] = None,
    status: Optional[str] = None,
    user: User = Depends(require_permission("communication:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """List all game sessions across types."""
    sessions = []
    for s in GAME_SESSIONS.values():
        if s["organization_id"] != org.id:
            continue
        if game_type and s["game_type"] != game_type:
            continue
        if status and s["status"] != status:
            continue
        sessions.append(GameListItem(
            id=s["id"],
            game_type=s["game_type"],
            title=s["title"],
            description=s.get("description"),
            status=s["status"],
            player_count=len(s.get("players", {})),
            max_players=s["max_players"],
            created_by=s["created_by"],
            created_at=s["created_at"],
            is_public=s["is_public"],
        ))
    return sessions