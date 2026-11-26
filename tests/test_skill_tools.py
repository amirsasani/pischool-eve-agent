import unittest

from eve_agent.skill_tools import load_data_reliability_report


class SkillToolTests(unittest.TestCase):
    def test_reliability_skill_has_agent_skills_frontmatter(self) -> None:
        content = load_data_reliability_report.invoke({})
        frontmatter = content.split("---", 2)[1]

        self.assertIn("name: data-reliability-report", frontmatter)
        self.assertIn("description:", frontmatter)
        self.assertIn("Do not assign a numeric reliability score.", content)


if __name__ == "__main__":
    unittest.main()
