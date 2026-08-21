import json
import unittest
from unittest.mock import Mock

from copilot.tools import ToolInvocation

from clients.ado_client import AdoClient
from tools.ado_tools import create_ado_tools


class AdoToolsTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_pr_details_returns_only_agent_relevant_fields(self) -> None:
        ado_client = Mock(spec=AdoClient)
        ado_client.get_pr.return_value = {
            "pullRequestId": 123,
            "title": "Improve request handling",
            "status": "active",
            "sourceRefName": "refs/heads/feature/request-handling",
            "targetRefName": "refs/heads/main",
            "createdBy": {
                "displayName": "Example Author",
                "uniqueName": "author@example.com",
            },
            "description": "This field should not be returned.",
            "repository": {"id": "internal-repository-id"},
        }
        get_pr_details, _ = create_ado_tools(ado_client)

        result = await get_pr_details.handler(
            ToolInvocation(arguments={"pull_request_id": 123})
        )

        self.assertEqual(
            json.loads(result.text_result_for_llm),
            {
                "id": 123,
                "title": "Improve request handling",
                "status": "active",
                "source_branch": "refs/heads/feature/request-handling",
                "target_branch": "refs/heads/main",
                "author": "Example Author",
            },
        )
        ado_client.get_pr.assert_called_once_with(123)

    async def test_get_pr_diff_returns_structured_file_changes(self) -> None:
        ado_client = Mock(spec=AdoClient)
        ado_client.get_pr_diff.return_value = (
            "--- /dev/null\n"
            "+++ b/new.py\n"
            "@@ -0,0 +1 @@\n"
            "+print('new')\n"
            "--- a/old.py\n"
            "+++ /dev/null\n"
            "@@ -1 +0,0 @@\n"
            "-print('old')\n"
        )
        _, get_pr_diff = create_ado_tools(ado_client)

        result = await get_pr_diff.handler(
            ToolInvocation(arguments={"pull_request_id": 123})
        )

        self.assertEqual(
            json.loads(result.text_result_for_llm),
            {
                "files": [
                    {
                        "old_path": None,
                        "new_path": "/new.py",
                        "change_type": "added",
                        "diff": (
                            "--- /dev/null\n"
                            "+++ b/new.py\n"
                            "@@ -0,0 +1 @@\n"
                            "+print('new')\n"
                        ),
                    },
                    {
                        "old_path": "/old.py",
                        "new_path": None,
                        "change_type": "deleted",
                        "diff": (
                            "--- a/old.py\n"
                            "+++ /dev/null\n"
                            "@@ -1 +0,0 @@\n"
                            "-print('old')\n"
                        ),
                    },
                ]
            },
        )
        ado_client.get_pr_diff.assert_called_once_with(pull_request_id=123)

    async def test_tools_reject_non_positive_pull_request_ids(self) -> None:
        ado_client = Mock(spec=AdoClient)
        get_pr_details, _ = create_ado_tools(ado_client)

        result = await get_pr_details.handler(
            ToolInvocation(arguments={"pull_request_id": 0})
        )

        self.assertEqual(result.result_type, "failure")
        self.assertIn("greater than 0", result.text_result_for_llm)
        ado_client.get_pr.assert_not_called()

    def test_diff_tool_description_explains_when_to_use_it(self) -> None:
        ado_client = Mock(spec=AdoClient)
        _, get_pr_diff = create_ado_tools(ado_client)

        self.assertIn("added, deleted, and modified lines", get_pr_diff.description)
        self.assertIn("actual code changes", get_pr_diff.description)


if __name__ == "__main__":
    unittest.main()
