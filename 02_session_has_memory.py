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
    response = await session.send_and_wait(prompt="I prefer probiotic beverages over aerated drinks.")
    logger.info(f"Copilot: {response.data.content}")

    response = await session.send_and_wait(prompt="List my preference for these drinks. 1. Coca-Cola, 2. Sprite 3. Kombucha")
    logger.info(f"Copilot: {response.data.content}")
    await client.stop()


if __name__ == "__main__":
    asyncio.run(main())
