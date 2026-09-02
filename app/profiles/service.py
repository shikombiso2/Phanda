from app.core.models import Profile


def compute_profile_completeness(profile: Profile) -> int:
    fields = [
        profile.job_type.value if profile.job_type else None,
        profile.location,
        profile.open_to_remote,
        profile.skills,
        profile.industries,
        profile.education_level,
        profile.experience_level.value if profile.experience_level else None,
        profile.desired_salary_min,
        profile.desired_salary_max,
        profile.active_cv_version_id or profile.cv_file_url,
    ]
    completed = sum(1 for value in fields if value is not None and value != [] and value != "")
    return round(completed / len(fields) * 100)
