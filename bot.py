import discord
from discord.ext import commands
import asyncio
import logging
import os

from config import BOT_TOKEN, COMMAND_PREFIX

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('discord_bot')

# Set up intents
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.reactions = True

# Create bot instance
bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)


@bot.event
async def on_ready():
    logger.info(f'{bot.user} has connected to Discord!')
    logger.info(f'Bot is in {len(bot.guilds)} guild(s)')
    
    # Sync slash commands - guild-specific for instant availability
    try:
        for guild in bot.guilds:
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            logger.info(f'Synced {len(synced)} slash command(s) to {guild.name}')
    except Exception as e:
        logger.error(f'Failed to sync commands: {e}')


async def main():
    async with bot:
        await bot.load_extension('cogs.music')
        await bot.start(BOT_TOKEN)


if __name__ == '__main__':
    asyncio.run(main())
