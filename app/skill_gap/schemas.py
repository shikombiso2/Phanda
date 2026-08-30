from pydantic import BaseModel


class SkillGapOut(BaseModel):
    missing_skills: list[str]


class RoadmapOut(BaseModel):
    skill: str
    resources: list[dict[str, str]]
    access_reason: str

