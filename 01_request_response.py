import asyncio
import logging

from copilot.client import CopilotClient
from copilot.session import PermissionHandler

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    force=True
)
logger = logging.getLogger(__name__)


async def main():
    client = CopilotClient()
    await client.start()

    session = await client.create_session(
        on_permission_request=PermissionHandler.approve_all
    )
    response = await session.send_and_wait(prompt="What files are present in the parent directory?")
    logger.info(response.data)
    await client.stop()


if __name__ == "__main__":
    asyncio.run(main())
