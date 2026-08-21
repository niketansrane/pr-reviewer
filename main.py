import argparse
import asyncio
import logging

from copilot import CopilotClient, SessionEvent, SessionEventType
from copilot.session import PermissionHandler, SystemMessageAppendConfig
from copilot.session_events import ToolExecutionCompleteData, ToolExecutionStartData

from clients.ado_client import AdoClient
from tools.ado_tools import create_ado_tools

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


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


async def main(pull_request_id: int):
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
        f"Get details of Azure Devops Pull Request: {pull_request_id}",
        timeout=300,
    )
    await client.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Review an Azure DevOps pull request.")
    parser.add_argument(
        "pull_request_id", type=int, help="Azure DevOps pull request ID"
    )
    args = parser.parse_args()
    asyncio.run(main(args.pull_request_id))
