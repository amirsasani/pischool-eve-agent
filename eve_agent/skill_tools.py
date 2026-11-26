"""On-demand Agent Skills exposed as local agent tools."""

from pathlib import Path

from langchain_core.tools import tool

SKILL_FILE = (
    Path(__file__).resolve().parent.parent
    / "skills"
    / "data-reliability-report"
    / "SKILL.md"
)


@tool
def load_data_reliability_report() -> str:
    """Load the skill for requests to assess an analysis's reliability, evidence, or limitations."""
    content = SKILL_FILE.read_text(encoding="utf-8")
    if not content.startswith("---\n") or "\n---\n" not in content[4:]:
        raise ValueError(f"Invalid Agent Skill frontmatter in {SKILL_FILE}")
    return content
