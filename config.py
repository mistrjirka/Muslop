import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
COMMAND_PREFIX = "!"

# Music folder is a subfolder within this project
PROJECT_DIR = Path(__file__).parent
MUSIC_FOLDER = PROJECT_DIR / "music"

if not BOT_TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN environment variable is not set!")
