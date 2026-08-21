import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from copilot import CopilotClient, SessionEvent, SessionEventType, Tool
from copilot.session import PermissionHandler, SystemMessageAppendConfig
from copilot.session_events import ToolExecutionCompleteData, ToolExecutionStartData
from copilot.tools import define_tool
from pydantic import BaseModel, Field

from clients.ado_client import AdoClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


class GetPullRequestParams(BaseModel):
    pull_request_id: int = Field(description="Pull Request Identifier")


class GetPullRequestDiffParams(BaseModel):
    pull_request_id: int = Field(description="Pull Request Identifier")


def create_ado_tools(ado_client: AdoClient) -> list[Tool]:
    @define_tool(description="Get Azure Devops Pull Request Details")
    def get_pr_details(params: GetPullRequestParams) -> dict[str, Any]:
        pull_request_id = params.pull_request_id
        return ado_client.get_pr(pull_request_id)

    @define_tool(description="Get Azure Devops Pull Request Diff changes")
    def get_pr_diff(params: GetPullRequestDiffParams) -> str:
        pull_request_id = params.pull_request_id
        return ado_client.get_pr_diff(pull_request_id=pull_request_id)

    return [get_pr_details, get_pr_diff]


def handle_event(event: SessionEvent):
    if event.type == SessionEventType.ASSISTANT_MESSAGE_DELTA:
        print(event.data.delta_content, flush=True, end="")
    elif event.type == SessionEventType.TOOL_EXECUTION_START and isinstance(
        event.data, ToolExecutionStartData
    ):
        logger.info(
            "Tool execution started: %s with arguments %s",
            event.data.tool_name,
            event.data.arguments,
        )
    elif event.type == SessionEventType.TOOL_EXECUTION_COMPLETE and isinstance(
        event.data, ToolExecutionCompleteData
    ):
        logger.info("Tool execution result: %s", event.data.success)
    elif event.type == SessionEventType.ASSISTANT_IDLE:
        print()


async def main():
    client = CopilotClient()
    await client.start()

    ado_client = AdoClient()
    ado_tools = create_ado_tools(ado_client)

    session = await client.create_session(
        on_permission_request=PermissionHandler.approve_all,
        tools=ado_tools,
        system_message=SystemMessageAppendConfig(
            content="""
            You are a senior software engineer who has a knack of identifying bottlenecks in the code and improve the code.
            When answering questions:
                - Be precice.
                - Explain your reasoning clearly.
                - Prefer Practical examples.
                - Do not invent information.
            """
        ),
    )
    session.on(handle_event)

    await session.send_and_wait(
        "Get details of Azure Devops Pull Request: 123", timeout=300
    )
    await client.stop()


if __name__ == "__main__":
    asyncio.run(main())
