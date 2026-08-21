import asyncio
import logging

from copilot.client import CopilotClient
from copilot.generated.session_events import SessionEventType
from copilot.session import PermissionHandler
from copilot.session_events import SessionEvent

logging.basicConfig(level=logging.INFO, format="%(message)s", force=True)
logger = logging.getLogger(__name__)


def handle_event(event: SessionEvent):
    if event.type == SessionEventType.ASSISTANT_MESSAGE_DELTA:
        print(
            event.data.delta_content, end="", flush=True
        )  # flush true means python can directly dump to console instead of otpimising and showing "batched" content.


async def main():
    client = CopilotClient()
    await client.start()

    session = await client.create_session(
        on_permission_request=PermissionHandler.approve_all
    )

    session.on(handle_event)

    user_input = "My name is Niketan. Tell me your name!"
    while True:
        if user_input.lower() == "exit":
            break
        await session.send_and_wait(prompt=user_input)
        user_input = input("User: ")
        # logger.info(f"Copilot: {response.data.content}")
    await client.stop()


if __name__ == "__main__":
    asyncio.run(main())
