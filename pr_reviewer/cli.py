"""Command-line interface for the pull-request reviewer."""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Sequence

from copilot import SessionEvent, SessionEventType
from copilot.session_events import ToolExecutionCompleteData, ToolExecutionStartData
from dotenv import load_dotenv

from pr_reviewer.ado_client import AdoClient
from pr_reviewer.reviewer import REVIEW_TIMEOUT_SECONDS, review_pull_request

logger = logging.getLogger(__name__)


def positive_integer(value: str) -> int:
    """Parse a positive integer for argparse."""

    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ado-pr-review",
        description="Review an Azure DevOps pull request with GitHub Copilot.",
    )
    parser.add_argument(
        "pull_request_id", type=positive_integer, help="pull request ID"
    )
    parser.add_argument(
        "--organization",
        help="Azure DevOps organization (defaults to ADO_ORGANIZATION)",
    )
    parser.add_argument(
        "--timeout",
        type=positive_integer,
        default=REVIEW_TIMEOUT_SECONDS,
        help=f"review timeout in seconds (default: {REVIEW_TIMEOUT_SECONDS})",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="show Azure DevOps tool execution details",
    )
    return parser


def handle_event(event: SessionEvent) -> None:
    """Render streaming session events for terminal users."""

    if event.type == SessionEventType.ASSISTANT_MESSAGE_DELTA:
        print(event.data.delta_content, flush=True, end="")
    elif event.type == SessionEventType.TOOL_EXECUTION_START and isinstance(
        event.data, ToolExecutionStartData
    ):
        logger.info("Running Azure DevOps tool: %s", event.data.tool_name)
    elif event.type == SessionEventType.TOOL_EXECUTION_COMPLETE and isinstance(
        event.data, ToolExecutionCompleteData
    ):
        logger.info(
            "Azure DevOps tool %s",
            "completed" if event.data.success else "failed",
        )
    elif event.type == SessionEventType.ASSISTANT_IDLE:
        print()


async def run(args: argparse.Namespace) -> None:
    """Create dependencies and run one review."""

    with AdoClient(organization=args.organization) as ado_client:
        await review_pull_request(
            args.pull_request_id,
            ado_client,
            on_event=handle_event,
            timeout=args.timeout,
        )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""

    load_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )

    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        logger.error("Review cancelled")
        return 130
    except Exception as error:  # The SDK does not expose one public base exception.
        if args.verbose:
            logger.exception("Review failed")
        else:
            logger.error("%s", error)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
