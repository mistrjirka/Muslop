import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
COMMAND_PREFIX = "!"

if not BOT_TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN environment variable is not set!")
