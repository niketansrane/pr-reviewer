import asyncio
import logging

from copilot.client import CopilotClient
from copilot.generated.session_events import SessionEventType
from copilot.session import (
    PermissionHandler,
    SystemMessageAppendConfig,
)
from copilot.session_events import SessionEvent

logging.basicConfig(level=logging.INFO, format="%(message)s", force=True)
logger = logging.getLogger(__name__)


def handle_event(event: SessionEvent):
    if event.type == SessionEventType.ASSISTANT_MESSAGE_DELTA:
        print(
            event.data.delta_content, end="", flush=True
        )  # flush true means python can directly dump to console instead of otpimising and showing "batched" content.
    if event.type == SessionEventType.SESSION_IDLE:
        print()


async def main():
    client = CopilotClient()
    await client.start()

    session = await client.create_session(
        on_permission_request=PermissionHandler.approve_all,
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

    await session.send_and_wait(prompt="Explain what is pull request?")

    logger.info(
        "\n\n ============= New Session with Kindergarten Teacher persona (using system prompt)! ============= \n\n"
    )

    session = await client.create_session(
        on_permission_request=PermissionHandler.approve_all,
        system_message=SystemMessageAppendConfig(
            content="""
            You are a kindergarden teacher who can explain any concept to toddlers using real life example.
            While answering questions,
            - Be creative.
            - Have a real-life example that toddlers can relate to.
            - Be short.
            """
        ),
    )
    session.on(handle_event)

    await session.send_and_wait(prompt="Explain what is pull request?")
    await client.stop()


if __name__ == "__main__":
    asyncio.run(main())
