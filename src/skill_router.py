"""
Skill router: discovers any skill with a SKILL.md (frontmatter description +
triggers) under src/skills/, and routes a batch of notes to the best-matching
department — replacing a hardcoded DEPARTMENT=.env value.

Uses LLM-based routing: one cheap LLM call per batch, asks the model to pick
from the discovered skill descriptions.
"""
import re
from pathlib import Path
from typing import Dict, List, Optional

import yaml


SKILLS_DIR = Path(__file__).parent / "skills"


def discover_skills() -> Dict[str, Dict]:
    """
    Scan src/skills/*/SKILL.md, parse YAML frontmatter only (cheap — no
    importing of fields.py/prompt.py here, that happens later via skill_loader
    once a department is chosen).

    Returns: {skill_name: {"description": str, "dir": Path}}
    """
    skills = {}
    if not SKILLS_DIR.exists():
        return skills

    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        md_path = skill_dir / "SKILL.md"
        if not md_path.exists():
            continue

        text = md_path.read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
        if not match:
            continue

        if yaml is None:
            raise ImportError("PyYAML is required for skill routing. Please install PyYAML.")
        meta = yaml.safe_load(match.group(1))

        name = meta.get("name", skill_dir.name)
        skills[name] = {
            "description": meta.get("description", "").strip(),
            "dir": skill_dir,
        }

    return skills


def route_notes_llm(notes: List[str], skills: Optional[Dict] = None, client=None, model: str = None) -> str:
    """
    LLM-based routing: one call, gives the model each skill's description and
    a sample of notes, asks it to pick the best-matching skill name only.
    Requires an OpenAI-compatible `client` (e.g. OpenRouter) and `model`.
    """
    skills = skills or discover_skills()
    if not skills:
        raise RuntimeError("No skills found under src/skills/*/SKILL.md")
    if client is None or model is None:
        raise ValueError("route_notes_llm requires an initialized client and model")

    options = "\n".join(f"- {name}: {meta['description']}" for name, meta in skills.items())
    sample = "\n---\n".join(notes[:3])[:1500]

    resp = client.chat.completions.create(
        model=model,
        messages=[{
            "role": "user",
            "content": (
                "You are a routing classifier. Given the skill options below and a "
                "sample of clinical notes, reply with ONLY the matching skill name "
                "(no explanation, no punctuation).\n\n"
                f"Skill options:\n{options}\n\n"
                f"Note sample:\n{sample}"
            ),
        }],
        temperature=0,
        max_tokens=10,
    )
    choice = resp.choices[0].message.content.strip().lower()
    return choice if choice in skills else next(iter(skills))


def route_notes(
    notes: List[str],
    client=None,
    model: str = None,
) -> str:
    """
    Single entrypoint used by main.py. Uses LLM-based routing.
    """
    skills = discover_skills()
    return route_notes_llm(notes, skills=skills, client=client, model=model)
