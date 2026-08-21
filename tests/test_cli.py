import argparse
import unittest
from unittest.mock import AsyncMock, Mock, patch

from pr_reviewer.cli import build_parser, main, run


class CliTests(unittest.IsolatedAsyncioTestCase):
    def test_parser_rejects_non_positive_pull_request_id(self) -> None:
        parser = build_parser()

        with self.assertRaises(SystemExit):
            parser.parse_args(["0"])

    async def test_run_closes_ado_client_after_review(self) -> None:
        args = argparse.Namespace(
            pull_request_id=123,
            organization="example-org",
            timeout=60,
        )
        ado_client = Mock()
        context_manager = Mock()
        context_manager.__enter__ = Mock(return_value=ado_client)
        context_manager.__exit__ = Mock(return_value=None)

        with (
            patch("pr_reviewer.cli.AdoClient", return_value=context_manager),
            patch(
                "pr_reviewer.cli.review_pull_request", new_callable=AsyncMock
            ) as review,
        ):
            await run(args)

        review.assert_awaited_once()
        context_manager.__exit__.assert_called_once()

    def test_main_returns_error_code_for_configuration_error(self) -> None:
        with (
            patch(
                "pr_reviewer.cli.run",
                new_callable=AsyncMock,
                side_effect=ValueError("bad config"),
            ),
            patch("pr_reviewer.cli.logger.error"),
        ):
            exit_code = main(["123"])

        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
