"""Phase 2 — People & Organization schemas."""

from datetime import date, datetime
from typing import Any, List, Optional

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel


# --------------------------------------------------------------------------- Employees

class EmployeeCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=150)
    last_name: Optional[str] = Field(default=None, max_length=150)
    display_name: Optional[str] = Field(default=None, max_length=255)
    email: EmailStr
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    employee_number: Optional[str] = None
    designation: Optional[str] = None
    department_id: Optional[str] = None
    team_id: Optional[str] = None
    manager_id: Optional[str] = None
    location_id: Optional[str] = None
    business_unit_id: Optional[str] = None
    employment_type: str = "full_time"
    joining_date: Optional[date] = None
    timezone: str = "UTC"
    language: Optional[str] = "en"
    bio: Optional[str] = None
    emergency_contact: Optional[dict[str, Any]] = None


class EmployeeUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    display_name: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    designation: Optional[str] = None
    department_id: Optional[str] = None
    team_id: Optional[str] = None
    manager_id: Optional[str] = None
    location_id: Optional[str] = None
    business_unit_id: Optional[str] = None
    employment_type: Optional[str] = None
    joining_date: Optional[date] = None
    timezone: Optional[str] = None
    language: Optional[str] = None
    bio: Optional[str] = None
    emergency_contact: Optional[dict[str, Any]] = None
    status: Optional[str] = Field(default=None, pattern="^(active|probation|notice|inactive)$")


class EmployeeSkillOut(ORMModel):
    id: str
    skill_id: str
    name: str
    category: Optional[str] = None
    level: int
    years_experience: float
    verified: bool


class EmployeeSkillAdd(BaseModel):
    skill_id: Optional[str] = None
    name: Optional[str] = None  # create-in-catalog shorthand
    level: int = Field(default=2, ge=1, le=5)
    years_experience: float = Field(default=0, ge=0, le=50)
    verified: bool = False


class CertificationOut(ORMModel):
    id: str
    name: str
    issuer: Optional[str] = None
    credential_id: Optional[str] = None
    issue_date: Optional[date] = None
    expiry_date: Optional[date] = None
    verified: bool


class CertificationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    issuer: Optional[str] = None
    credential_id: Optional[str] = None
    issue_date: Optional[date] = None
    expiry_date: Optional[date] = None
    verified: bool = False


class AchievementOut(ORMModel):
    id: str
    kind: str
    title: str
    description: Optional[str] = None
    achieved_on: Optional[date] = None


class AchievementCreate(BaseModel):
    kind: str = Field(default="recognition", pattern="^(award|recognition|milestone|learning|community|certification)$")
    title: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    achieved_on: Optional[date] = None


class TimelineOut(ORMModel):
    id: str
    kind: str
    title: str
    description: Optional[str] = None
    meta: Optional[dict[str, Any]] = None
    occurred_at: datetime


class AvailabilityOut(ORMModel):
    id: str
    employee_id: str
    status: str
    note: Optional[str] = None
    available_from: Optional[datetime] = None
    available_until: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AvailabilityUpdate(BaseModel):
    status: str = Field(pattern="^(available|busy|meeting|leave|focus|offline|remote|traveling)$")
    note: Optional[str] = None
    available_from: Optional[datetime] = None
    available_until: Optional[datetime] = None


class PresenceOut(ORMModel):
    id: str
    employee_id: str
    is_online: bool
    status: str
    last_active_at: Optional[datetime] = None
    working_hours: Optional[dict[str, Any]] = None
    timezone: Optional[str] = None
    device: Optional[str] = None
    updated_at: Optional[datetime] = None


class PresenceUpdate(BaseModel):
    status: Optional[str] = Field(default=None, pattern="^(online|away|busy|offline)$")
    working_hours: Optional[dict[str, Any]] = None
    timezone: Optional[str] = None
    device: Optional[str] = None


class EmployeeSummary(ORMModel):
    id: str
    employee_number: str
    first_name: str
    last_name: Optional[str] = None
    display_name: Optional[str] = None
    full_name: str
    email: str
    avatar_url: Optional[str] = None
    designation: Optional[str] = None
    department_id: Optional[str] = None
    department_name: Optional[str] = None
    team_id: Optional[str] = None
    team_name: Optional[str] = None
    manager_id: Optional[str] = None
    manager_name: Optional[str] = None
    location_id: Optional[str] = None
    location_name: Optional[str] = None
    employment_type: str
    joining_date: Optional[date] = None
    status: str
    timezone: str
    expertise_score: float = 0.0
    profile_completion: int = 0
    availability_status: Optional[str] = None
    presence_status: Optional[str] = None
    is_online: bool = False
    top_skills: List[str] = []
    is_favorite: bool = False
    user_id: Optional[str] = None


class EmployeeOut(EmployeeSummary):
    user_id: Optional[str] = None
    phone: Optional[str] = None
    language: Optional[str] = None
    bio: Optional[str] = None
    emergency_contact: Optional[dict[str, Any]] = None
    business_unit_id: Optional[str] = None
    business_unit_name: Optional[str] = None
    ai_summary: Optional[str] = None
    skills: List[EmployeeSkillOut] = []
    certifications: List[CertificationOut] = []
    achievements: List[AchievementOut] = []
    timeline_count: int = 0
    reports_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class EmployeeDelete(BaseModel):
    reason: Optional[str] = None


# --------------------------------------------------------------------------- Departments

class DepartmentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    code: str = Field(min_length=2, max_length=60, pattern=r"^[a-z0-9_-]+$")
    description: Optional[str] = None
    parent_id: Optional[str] = None
    head_id: Optional[str] = None
    location_id: Optional[str] = None


class DepartmentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    parent_id: Optional[str] = None
    head_id: Optional[str] = None
    location_id: Optional[str] = None


class DepartmentOut(ORMModel):
    id: str
    name: str
    code: str
    description: Optional[str] = None
    parent_id: Optional[str] = None
    parent_name: Optional[str] = None
    head_id: Optional[str] = None
    head_name: Optional[str] = None
    location_id: Optional[str] = None
    location_name: Optional[str] = None
    members_count: int = 0
    teams_count: int = 0
    children: List["DepartmentOut"] = []


class DepartmentStats(BaseModel):
    department_id: str
    department_name: str
    members: int
    teams: int
    avg_expertise: float
    skills: List[dict[str, Any]] = []


# --------------------------------------------------------------------------- Teams

class TeamCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    code: str = Field(min_length=2, max_length=60, pattern=r"^[a-z0-9_-]+$")
    description: Optional[str] = None
    department_id: Optional[str] = None
    lead_id: Optional[str] = None


class TeamUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    department_id: Optional[str] = None
    lead_id: Optional[str] = None


class TeamMemberOut(BaseModel):
    id: str
    employee_id: str
    employee_name: str
    designation: Optional[str] = None
    avatar_url: Optional[str] = None
    role: Optional[str] = None
    joined_at: Optional[datetime] = None
    is_primary: bool = False


class TeamOut(ORMModel):
    id: str
    name: str
    code: str
    description: Optional[str] = None
    department_id: Optional[str] = None
    department_name: Optional[str] = None
    lead_id: Optional[str] = None
    lead_name: Optional[str] = None
    members_count: int = 0
    members: List[TeamMemberOut] = []


# --------------------------------------------------------------------------- Structure

class LocationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    code: str = Field(min_length=2, max_length=60, pattern=r"^[a-z0-9_-]+$")
    city: Optional[str] = None
    country: Optional[str] = None
    address: Optional[str] = None
    is_office: bool = True
    timezone: Optional[str] = None


class LocationOut(ORMModel):
    id: str
    name: str
    code: str
    city: Optional[str] = None
    country: Optional[str] = None
    address: Optional[str] = None
    is_office: bool
    timezone: Optional[str] = None
    employees_count: int = 0


class BusinessUnitCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    code: str = Field(min_length=2, max_length=60, pattern=r"^[a-z0-9_-]+$")
    description: Optional[str] = None
    head_id: Optional[str] = None
    parent_id: Optional[str] = None


class BusinessUnitOut(ORMModel):
    id: str
    name: str
    code: str
    description: Optional[str] = None
    head_id: Optional[str] = None
    head_name: Optional[str] = None
    parent_id: Optional[str] = None
    employees_count: int = 0


class OrganizationStructure(BaseModel):
    departments: List[DepartmentOut] = []
    teams: List[TeamOut] = []
    locations: List[LocationOut] = []
    business_units: List[BusinessUnitOut] = []


# --------------------------------------------------------------------------- Org chart

class OrgChartNode(BaseModel):
    id: str
    employee_number: str
    name: str
    designation: Optional[str] = None
    department: Optional[str] = None
    team: Optional[str] = None
    avatar_url: Optional[str] = None
    is_online: bool = False
    children: List["OrgChartNode"] = []


class OrgChartResponse(BaseModel):
    root: Optional[OrgChartNode] = None
    roots: List[OrgChartNode] = []
    total: int
    max_depth: int


class GraphEdge(BaseModel):
    source: str
    target: str
    relation: str  # manages | reports_to | member_of | leads | head_of | located_at


class GraphNode(BaseModel):
    id: str
    label: str
    kind: str  # employee | department | team | location
    designation: Optional[str] = None
    meta: dict[str, Any] = {}


class OrganizationGraph(BaseModel):
    nodes: List[GraphNode] = []
    edges: List[GraphEdge] = []


# --------------------------------------------------------------------------- Expertise

class SkillOut(ORMModel):
    id: str
    name: str
    category: Optional[str] = None
    description: Optional[str] = None
    employees_count: int = 0


class SkillCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: Optional[str] = None
    description: Optional[str] = None


class ExpertiseScoreOut(ORMModel):
    id: str
    employee_id: str
    skill_id: str
    skill_name: str
    category: Optional[str] = None
    score: float
    level: int
    years_experience: float
    factors: Optional[dict[str, Any]] = None
    updated_at: Optional[datetime] = None


class ExpertOut(BaseModel):
    employee_id: str
    employee_number: str
    name: str
    designation: Optional[str] = None
    department: Optional[str] = None
    team: Optional[str] = None
    avatar_url: Optional[str] = None
    skill: str
    score: float
    level: int
    years_experience: float
    is_online: bool = False


class SuccessorOut(BaseModel):
    employee_id: str
    employee_number: str
    name: str
    designation: Optional[str] = None
    department: Optional[str] = None
    avatar_url: Optional[str] = None
    score: float
    reasons: List[str] = []


class MentorOut(BaseModel):
    employee_id: str
    name: str
    designation: Optional[str] = None
    skill: str
    score: float
    years_experience: float


class SkillGap(BaseModel):
    skill: str
    category: Optional[str] = None
    demand: int
    supply: int
    ratio: float


# --------------------------------------------------------------------------- Intelligence

class OrgIntelligence(BaseModel):
    total_employees: int
    active_employees: int
    departments: int
    teams: int
    locations: int
    business_units: int
    managers: int
    avg_expertise: float
    avg_profile_completion: float
    online_now: int
    on_leave: int
    recent_joins: List[dict[str, Any]] = []
    recent_transfers: List[dict[str, Any]] = []
    department_distribution: List[dict[str, Any]] = []
    team_distribution: List[dict[str, Any]] = []
    location_distribution: List[dict[str, Any]] = []
    skill_distribution: List[dict[str, Any]] = []
    growth_30d: int = 0
    growth_90d: int = 0
    reporting_depth: int = 0
    management_span: float = 0.0
    org_health: int = 0


# --------------------------------------------------------------------------- Favorites

class FavoriteOut(ORMModel):
    id: str
    employee_id: str
    target_employee_id: str
    created_at: Optional[datetime] = None


class ProfileCompletionBreakdown(BaseModel):
    score: int
    fields: dict[str, bool] = {}
