"""
Skill loader: resolves a department/skill name to its REQUIRED_FIELDS,
SYSTEM_PROMPT (the body of skills/<name>/SKILL.md, after frontmatter),
get_user_prompt(), and scoring function.

Department is no longer hardcoded — any folder under src/skills/ with a
SKILL.md is a valid, loadable skill. Use skill_router.discover_skills() to
see what's available and skill_router.route_notes() to pick one automatically.
"""
import importlib
import re
from pathlib import Path
from typing import Dict


def available_departments() -> list:
    """Any folder under src/skills/ containing a SKILL.md is a valid department."""
    skills_dir = Path(__file__).parent / "skills"
    return sorted(
        p.name.upper() for p in skills_dir.iterdir()
        if p.is_dir() and (p / "SKILL.md").exists()
    )


def load_skill(department: str) -> Dict:
    """
    Returns a dict with:
      - required_fields: List[str]
      - field_aliases: Dict[str, str]
      - system_prompt: str          (SKILL.md body, frontmatter stripped)
      - get_user_prompt: Callable
      - scoring_fn: Callable(record, actual_icd10=None) -> float
    """
    department = department.strip().upper()
    valid = available_departments()
    if department not in valid:
        raise ValueError(f"Unknown department '{department}'. Available: {valid}")

    skill_dir = Path(__file__).parent / "skills" / department.lower()
    md_path = skill_dir / "SKILL.md"
    if not md_path.exists():
        raise FileNotFoundError(f"Missing skill file: {md_path}")

    text = md_path.read_text(encoding="utf-8")
    match = re.match(r"^---\n.*?\n---\n(.*)$", text, re.DOTALL)
    system_prompt = match.group(1).strip() if match else text.strip()

    pkg = f"src.skills.{department.lower()}"
    fields_mod = importlib.import_module(f"{pkg}.fields")
    prompt_mod = importlib.import_module(f"{pkg}.prompt")

    return {
        "required_fields": fields_mod.REQUIRED_FIELDS,
        "field_aliases": getattr(fields_mod, "FIELD_ALIASES", {}),
        "system_prompt": system_prompt,
        "get_user_prompt": prompt_mod.get_user_prompt,
        "scoring_fn": fields_mod.scoring_fn,
    }
