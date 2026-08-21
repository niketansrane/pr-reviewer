"""Copilot orchestration for Azure DevOps pull-request reviews."""

from __future__ import annotations

from collections.abc import Callable
from tempfile import TemporaryDirectory

from copilot import CopilotClient, SessionEvent
from copilot.session import SystemMessageAppendConfig

from pr_reviewer.ado_client import AdoClient
from pr_reviewer.ado_tools import create_ado_tools

REVIEW_TIMEOUT_SECONDS = 300
SYSTEM_PROMPT = """You are a senior software engineer reviewing an Azure DevOps pull request.
Use the provided tools to inspect both the pull-request metadata and its complete diff.
Report only findings supported by the diff. Prioritize correctness, security, reliability,
and maintainability. For each finding, name the affected file, explain the impact, and
suggest a concrete fix. If no issues are found, say so clearly. Be concise.
"""


async def review_pull_request(
    pull_request_id: int,
    ado_client: AdoClient,
    *,
    on_event: Callable[[SessionEvent], None] | None = None,
    timeout: int = REVIEW_TIMEOUT_SECONDS,
) -> None:
    """Run a read-only Copilot review and stream events to ``on_event``."""

    if pull_request_id <= 0:
        raise ValueError("pull_request_id must be greater than zero")
    if timeout <= 0:
        raise ValueError("timeout must be greater than zero")

    tools = create_ado_tools(ado_client)
    tool_names = [tool.name for tool in tools]
    # Empty mode deliberately avoids the user's global ~/.copilot storage and
    # requires an explicit, tenant-scoped location. This reviewer has no state
    # to preserve, so isolate each invocation in a short-lived directory.
    with TemporaryDirectory(prefix="ado-pr-review-") as base_directory:
        client = CopilotClient(mode="empty", base_directory=base_directory)

        await client.start()
        try:
            session = await client.create_session(
                tools=tools,
                available_tools=tool_names,
                system_message=SystemMessageAppendConfig(content=SYSTEM_PROMPT),
                on_event=on_event,
            )
            await session.send_and_wait(
                f"Review Azure DevOps pull request {pull_request_id}.",
                timeout=timeout,
            )
        finally:
            await client.stop()
