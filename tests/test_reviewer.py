import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from pr_reviewer.reviewer import review_pull_request


class ReviewerTests(unittest.IsolatedAsyncioTestCase):
    async def test_stops_copilot_client_when_review_fails(self) -> None:
        ado_client = Mock()
        session = Mock()
        session.send_and_wait = AsyncMock(side_effect=RuntimeError("review failed"))
        copilot_client = Mock()
        copilot_client.start = AsyncMock()
        copilot_client.create_session = AsyncMock(return_value=session)
        copilot_client.stop = AsyncMock()

        with (
            patch(
                "pr_reviewer.reviewer.CopilotClient", return_value=copilot_client
            ) as client_class,
            self.assertRaisesRegex(RuntimeError, "review failed"),
        ):
            await review_pull_request(123, ado_client)

        client_class.assert_called_once()
        client_options = client_class.call_args.kwargs
        self.assertEqual(client_options["mode"], "empty")
        base_directory = Path(client_options["base_directory"])
        self.assertTrue(base_directory.name.startswith("ado-pr-review-"))
        self.assertFalse(base_directory.exists())
        copilot_client.stop.assert_awaited_once_with()
        session.send_and_wait.assert_awaited_once_with(
            "Review Azure DevOps pull request 123.",
            timeout=300,
        )
        session_config = copilot_client.create_session.await_args.kwargs
        self.assertEqual(
            session_config["available_tools"], ["get_pr_details", "get_pr_diff"]
        )
        self.assertNotIn("on_permission_request", session_config)

    async def test_rejects_invalid_pull_request_id_before_starting_client(self) -> None:
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            await review_pull_request(0, Mock())


if __name__ == "__main__":
    unittest.main()
