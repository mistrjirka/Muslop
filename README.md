# Discord Music Bot

A Discord music bot that plays audio from YouTube using yt-dlp Python bindings.

## Setup

1. **Create a virtual environment and install dependencies:**
   ```bash
   cd /home/jirka/programovani/discordbot
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Install FFmpeg** (required for audio streaming):
   ```bash
   sudo apt install ffmpeg
   ```

3. **Set up your Discord bot token:**
   - Go to https://discord.com/developers/applications
   - Create a new application and add a bot
   - Copy the bot token
   - Create a `.env` file (use `.env.example` as template):
     ```
     DISCORD_BOT_TOKEN=your_token_here
     ```

4. **Invite the bot to your server:**
   - In Discord Developer Portal, go to OAuth2 → URL Generator
   - Select scopes: `bot`, `applications.commands`
   - Select permissions: `Connect`, `Speak`, `Send Messages`, `Read Message History`
   - Use the generated URL to invite the bot

## Usage

Run the bot:
```bash
source venv/bin/activate
python bot.py
```

### Commands

| Command | Aliases | Description |
|---------|---------|-------------|
| `!join` | `!j` | Join your voice channel |
| `!leave` | `!l`, `!dc` | Leave the voice channel |
| `!play <query>` | `!p` | Play audio from URL or search |
| `!pause` | - | Pause playback |
| `!resume` | `!unpause` | Resume playback |
| `!stop` | - | Stop and clear queue |
| `!skip` | `!s`, `!next` | Skip current song |
| `!queue` | `!q` | Show queue |
| `!nowplaying` | `!np` | Show current song |
| `!loop` | - | Toggle loop mode |

## Features

- ✅ Audio-only download (no video)
- ✅ Uses yt-dlp Python bindings (not CLI)
- ✅ Queue system with skip/pause/resume
- ✅ Search YouTube by query or URL
- ✅ Loop mode for current song
