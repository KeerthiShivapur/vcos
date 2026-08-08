"""Courses API (Phase 10.2 — Course Management).

Full CRUD over the course catalog plus modules, lessons and quizzes, and
the enrollment/progress pipeline (enroll, complete lesson, complete course,
quiz scoring for enrolled employees).
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.db.database import get_db
from app.learning.course_service import course_service
from app.learning.learning_path_service import learning_path_service
from app.models.course import CourseEnrollment, CourseModule, CourseQuiz, Lesson
from app.models.employee import Employee
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/learning/courses", tags=["Learning"])


async def _employee_id(db: AsyncSession, org: Organization, user: User) -> str:
    employee = (
        await db.execute(
            select(Employee).where(
                Employee.organization_id == org.id, Employee.user_id == str(user.id)
            )
        )
    ).scalar_one_or_none()
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee profile not found")
    return employee.id


async def _course_payload(course, enrollments=0, progress: Optional[float] = None, enrollment_id: Optional[str] = None) -> dict[str, Any]:
    return {
        "id": course.id,
        "title": course.title,
        "description": course.description,
        "category": course.category,
        "difficulty": course.difficulty,
        "duration_minutes": course.duration_minutes,
        "format": course.format,
        "department": course.department,
        "language": course.language,
        "status": course.status,
        "external_url": course.external_url,
        "cover_url": course.cover_url,
        "certificate_title": course.certificate_title,
        "skills": course.skills or [],
        "tags": course.tags or [],
        "enrollments": enrollments,
        "my_progress": progress,
        "my_enrollment_id": enrollment_id,
    }


# ------------------------------------------------------------------ catalog

@router.get("")
async def list_courses(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:read")),
    db: AsyncSession = Depends(get_db),
    category: str = Query(None),
    difficulty: str = Query(None),
    search: str = Query(None),
    status: str = Query("published"),
    limit: int = Query(50, ge=1, le=200),
):
    employee_id = await _employee_id(db, org, user)
    courses = await course_service.list_courses(
        db, organization_id=org.id, category=category, difficulty=difficulty,
        search=search, status=status, limit=limit,
    )
    result = []
    for course in courses:
        enrollment = (
            await db.execute(
                select(CourseEnrollment).where(
                    CourseEnrollment.organization_id == org.id,
                    CourseEnrollment.course_id == course.id,
                    CourseEnrollment.employee_id == employee_id,
                )
            )
        ).scalar_one_or_none()
        result.append(
            await _course_payload(
                course,
                enrollments=len(course.enrollments),
                progress=enrollment.progress if enrollment else None,
                enrollment_id=enrollment.id if enrollment else None,
            )
        )
    return result



@router.get("/categories", response_model=list[str])
async def course_categories(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:read")),
    db: AsyncSession = Depends(get_db),
):
    return await course_service.categories(db, organization_id=org.id)


@router.get("/trending")
async def trending_courses(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:read")),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(6, ge=1, le=20),
):
    courses = await course_service.trending(db, organization_id=org.id, limit=limit)
    return [
        {
            "id": course.id,
            "title": course.title,
            "category": course.category,
            "difficulty": course.difficulty,
            "duration_minutes": course.duration_minutes,
            "enrollments": len(course.enrollments),
        }
        for course in courses
    ]


@router.get("/{course_id}")
async def course_detail(
    course_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:read")),
    db: AsyncSession = Depends(get_db),
):
    course = await course_service.get_course(db, organization_id=org.id, course_id=course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    modules = (
        await db.execute(
            select(CourseModule)
            .where(CourseModule.organization_id == org.id, CourseModule.course_id == course.id)
            .order_by(CourseModule.position)
        )
    ).scalars().all()
    lessons = (
        await db.execute(
            select(Lesson)
            .where(Lesson.organization_id == org.id, Lesson.course_id == course.id)
            .order_by(Lesson.position)
        )
    ).scalars().all()
    quizzes = (
        await db.execute(
            select(CourseQuiz)
            .where(CourseQuiz.organization_id == org.id, CourseQuiz.course_id == course.id)
            .order_by(CourseQuiz.position)
        )
    ).scalars().all()
    payload = await _course_payload(course, enrollments=len(course.enrollments))
    payload["modules"] = [
        {
            "id": module.id,
            "title": module.title,
            "description": module.description,
            "position": module.position,
        }
        for module in modules
    ]
    payload["lessons"] = [
        {
            "id": lesson.id,
            "title": lesson.title,
            "module_id": lesson.module_id,
            "content_type": lesson.content_type,
            "external_url": lesson.external_url,
            "position": lesson.position,
            "duration_minutes": lesson.duration_minutes,
        }
        for lesson in lessons
    ]
    payload["quizzes"] = [
        {
            "id": quiz.id,
            "title": quiz.title,
            "module_id": quiz.module_id,
            "question_count": len(quiz.questions or []),
            "passing_score": quiz.passing_score,
        }
        for quiz in quizzes
    ]
    return payload


# ------------------------------------------------------------------ manage

@router.post("", status_code=201)
async def create_course(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:manage")),
    db: AsyncSession = Depends(get_db),
):
    course = await course_service.create_course(db, organization_id=org.id, data=payload)
    await db.commit()
    return await _course_payload(course)


@router.patch("/{course_id}")
async def update_course(
    course_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:manage")),
    db: AsyncSession = Depends(get_db),
):
    course = await course_service.update_course(db, organization_id=org.id, course_id=course_id, data=payload)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    await db.commit()
    return await _course_payload(course)


@router.delete("/{course_id}")
async def delete_course(
    course_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:manage")),
    db: AsyncSession = Depends(get_db),
):
    deleted = await course_service.delete_course(db, organization_id=org.id, course_id=course_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Course not found")
    await db.commit()
    return {"deleted": True}


@router.post("/{course_id}/modules", status_code=201)
async def add_module(
    course_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:manage")),
    db: AsyncSession = Depends(get_db),
):
    module = await course_service.add_module(
        db, organization_id=org.id, course_id=course_id,
        title=payload["title"], description=payload.get("description"),
        position=payload.get("position"),
    )
    if module is None:
        raise HTTPException(status_code=404, detail="Course not found")
    await db.commit()
    return {"id": module.id, "title": module.title, "position": module.position}


@router.post("/{course_id}/lessons", status_code=201)
async def add_lesson(
    course_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:manage")),
    db: AsyncSession = Depends(get_db),
):
    lesson = await course_service.add_lesson(
        db, organization_id=org.id, course_id=course_id,
        title=payload["title"], module_id=payload.get("module_id"),
        content=payload.get("content"), content_type=payload.get("content_type", "text"),
        external_url=payload.get("external_url"), duration_minutes=payload.get("duration_minutes", 0),
    )
    if lesson is None:
        raise HTTPException(status_code=404, detail="Course not found")
    await db.commit()
    return {"id": lesson.id, "title": lesson.title, "position": lesson.position}


@router.post("/{course_id}/quizzes", status_code=201)
async def add_quiz(
    course_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:manage")),
    db: AsyncSession = Depends(get_db),
):
    quiz = await course_service.add_quiz(
        db, organization_id=org.id, course_id=course_id,
        title=payload["title"], questions=payload.get("questions", []),
        module_id=payload.get("module_id"), passing_score=payload.get("passing_score", 70.0),
    )
    if quiz is None:
        raise HTTPException(status_code=404, detail="Course not found")
    await db.commit()
    return {"id": quiz.id, "title": quiz.title, "question_count": len(quiz.questions or [])}


# ------------------------------------------------------------------ enrollment & progress

@router.post("/{course_id}/enroll", status_code=201)
async def enroll(
    course_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    employee_id = await _employee_id(db, org, user)
    enrollment = await course_service.enroll(db, organization_id=org.id, course_id=course_id, employee_id=employee_id)
    if enrollment is None:
        raise HTTPException(status_code=404, detail="Course not available for enrollment")
    await db.commit()
    return {"id": enrollment.id, "course_id": course_id, "status": enrollment.status, "progress": enrollment.progress}


@router.get("/my/enrollments")
async def my_enrollments(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:read")),
    db: AsyncSession = Depends(get_db),
):
    employee_id = await _employee_id(db, org, user)
    enrollments = await course_service.my_enrollments(db, organization_id=org.id, employee_id=employee_id)
    result = []
    for enrollment in enrollments:
        course = await course_service.get_course(db, organization_id=org.id, course_id=enrollment.course_id)
        if course is None:
            continue
        result.append(
            {
                "id": enrollment.id,
                "course_id": course.id,
                "title": course.title,
                "category": course.category,
                "status": enrollment.status,
                "progress": enrollment.progress,
                "enrolled_at": enrollment.enrolled_at.isoformat(),
                "completed_at": enrollment.completed_at.isoformat() if enrollment.completed_at else None,
            }
        )
    return result


@router.post("/enrollments/{enrollment_id}/lessons/{lesson_id}/complete")
async def complete_lesson(
    enrollment_id: str,
    lesson_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    employee_id = await _employee_id(db, org, user)
    enrollment = await course_service.complete_lesson(
        db, organization_id=org.id, enrollment_id=enrollment_id,
        lesson_id=lesson_id, employee_id=employee_id,
    )
    if enrollment is None:
        raise HTTPException(status_code=404, detail="Enrollment or lesson not found")
    await db.commit()
    # auto-complete learning-path steps referencing this course
    await learning_path_service.auto_complete_course_steps(
        db, organization_id=org.id, employee_id=employee_id, course_id=enrollment.course_id
    )
    await db.commit()
    return {"id": enrollment.id, "status": enrollment.status, "progress": enrollment.progress}


@router.post("/enrollments/{enrollment_id}/complete")
async def complete_course(
    enrollment_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    employee_id = await _employee_id(db, org, user)
    enrollment = (
        await db.execute(
            select(CourseEnrollment).where(
                CourseEnrollment.organization_id == org.id,
                CourseEnrollment.id == enrollment_id,
                CourseEnrollment.employee_id == employee_id,
            )
        )
    ).scalar_one_or_none()
    if enrollment is None:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    result = await course_service.complete_course(db, organization_id=org.id, enrollment_id=enrollment.id)
    await db.commit()
    await learning_path_service.auto_complete_course_steps(
        db, organization_id=org.id, employee_id=employee_id, course_id=enrollment.course_id
    )
    await db.commit()
    return {"id": result.id, "status": result.status, "progress": result.progress}
