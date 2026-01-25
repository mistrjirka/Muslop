import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import yt_dlp
import os
from pathlib import Path
from collections import deque

from config import MUSIC_FOLDER

# Supported audio file extensions
AUDIO_EXTENSIONS = {'.mp3', '.wav', '.flac', '.ogg', '.m4a', '.opus', '.aac', '.wma'}

# yt-dlp options for audio-only extraction
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'extract_flat': False,
    'default_search': 'ytsearch',  # Enables YouTube search for plain text
}

# FFmpeg options for streaming audio
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',  # -vn means no video
}

# FFmpeg options for local files (no reconnect needed)
FFMPEG_LOCAL_OPTIONS = {
    'options': '-vn',
}

# Control emojis
EMOJI_PAUSE = '⏸️'
EMOJI_RESUME = '▶️'
EMOJI_SKIP = '⏭️'
EMOJI_STOP = '⏹️'
EMOJI_QUEUE = '📜'
EMOJI_NINJA = '🥷'  # Plays song #2
CONTROL_EMOJIS = [EMOJI_PAUSE, EMOJI_RESUME, EMOJI_SKIP, EMOJI_STOP, EMOJI_QUEUE, EMOJI_NINJA]


def get_local_songs():
    """Get list of audio files from the music folder."""
    songs = []
    music_path = Path(MUSIC_FOLDER)
    
    if not music_path.exists():
        return songs
    
    for file in sorted(music_path.iterdir()):
        if file.is_file() and file.suffix.lower() in AUDIO_EXTENSIONS:
            songs.append(file)
    
    return songs


class MusicPlayer:
    """Manages the music queue and playback for a guild."""
    
    def __init__(self):
        self.queue = deque()
        self.current = None
        self.loop = False
        self.now_playing_message = None
    
    def add(self, song):
        self.queue.append(song)
    
    def next(self):
        if self.loop and self.current:
            return self.current
        if self.queue:
            self.current = self.queue.popleft()
            return self.current
        self.current = None
        return None
    
    def clear(self):
        self.queue.clear()
        self.current = None


class Music(commands.Cog):
    """Music cog for playing YouTube audio in voice channels."""
    
    def __init__(self, bot):
        self.bot = bot
        self.players = {}  # guild_id -> MusicPlayer
    
    def get_player(self, guild_id):
        if guild_id not in self.players:
            self.players[guild_id] = MusicPlayer()
        return self.players[guild_id]
    
    async def extract_info(self, query):
        """Extract audio info using yt-dlp Python bindings (audio only).
        
        Supports:
        - Direct YouTube URLs
        - Plain text search (automatically searches YouTube and picks first result)
        """
        loop = asyncio.get_event_loop()
        
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            try:
                # Check if it's a URL or search query
                if not query.startswith(('http://', 'https://')):
                    # Plain text -> search YouTube for first result
                    query = f'ytsearch1:{query}'
                
                info = await loop.run_in_executor(
                    None, 
                    lambda: ydl.extract_info(query, download=False)
                )
                
                # Handle search results (ytsearch returns entries)
                if 'entries' in info:
                    if not info['entries']:
                        raise Exception('No results found')
                    info = info['entries'][0]
                
                return {
                    'url': info['url'],
                    'title': info.get('title', 'Unknown'),
                    'duration': info.get('duration', 0),
                    'thumbnail': info.get('thumbnail'),
                    'webpage_url': info.get('webpage_url', query),
                    'is_local': False,
                }
            except Exception as e:
                raise Exception(f'Failed to extract audio: {str(e)}')
    
    def get_local_song_info(self, song_number: int):
        """Get local song info by number (1-indexed)."""
        songs = get_local_songs()
        
        if not songs:
            raise Exception('No audio files found')
        
        if song_number < 1 or song_number > len(songs):
            raise Exception(f'Invalid song number. Choose 1-{len(songs)}')
        
        song_path = songs[song_number - 1]
        
        return {
            'url': str(song_path),
            'title': f'Song #{song_number}',  # Just show the number
            'duration': 0,
            'thumbnail': None,
            'webpage_url': None,
            'is_local': True,
        }
    
    async def send_now_playing(self, ctx, song):
        """Send a now playing message with reaction controls."""
        player = self.get_player(ctx.guild.id)
        
        embed = discord.Embed(
            title='🎵 Now Playing',
            description=f'**{song["title"]}**',
            color=discord.Color.green()
        )
        
        if song.get('thumbnail'):
            embed.set_thumbnail(url=song['thumbnail'])
        
        if song.get('duration') and song['duration'] > 0:
            minutes, seconds = divmod(song['duration'], 60)
            embed.add_field(name='Duration', value=f'{minutes}:{seconds:02d}')
        
        if song.get('is_local'):
            embed.add_field(name='Source', value='📁 Local File', inline=True)
        
        # Add control instructions
        embed.set_footer(text='⏸️ Pause | ▶️ Resume | ⏭️ Skip | ⏹️ Stop | 📜 Queue | 🥷 Play #2')
        
        # Send message and add reactions
        msg = await ctx.channel.send(embed=embed)
        player.now_playing_message = msg
        
        # Add control reactions
        for emoji in CONTROL_EMOJIS:
            try:
                await msg.add_reaction(emoji)
            except discord.HTTPException:
                pass
    
    async def play_next(self, ctx):
        """Play the next song in the queue."""
        player = self.get_player(ctx.guild.id)
        song = player.next()
        
        if song is None:
            return
        
        voice_client = ctx.guild.voice_client
        if voice_client is None or not voice_client.is_connected():
            return
        
        # Choose FFmpeg options based on source
        if song.get('is_local'):
            source = discord.FFmpegPCMAudio(song['url'], **FFMPEG_LOCAL_OPTIONS)
        else:
            source = discord.FFmpegPCMAudio(song['url'], **FFMPEG_OPTIONS)
        
        def after_playing(error):
            if error:
                print(f'Player error: {error}')
            # Schedule next song
            asyncio.run_coroutine_threadsafe(self.play_next(ctx), self.bot.loop)
        
        voice_client.play(source, after=after_playing)
        
        # Send now playing with controls
        await self.send_now_playing(ctx, song)
    
    async def connect_to_voice(self, ctx, member=None) -> bool:
        """Try to connect to voice channel with error handling.
        
        Works with both commands.Context and discord.Message (for reactions).
        """
        # Use provided member (for reactions) or ctx.author (for commands)
        user = member or getattr(ctx, 'author', None)
        
        if user is None or user.voice is None:
            send_func = ctx.send if hasattr(ctx, 'send') else ctx.channel.send
            await send_func('❌ You must be in a voice channel!')
            return False
        
        channel = user.voice.channel
        
        try:
            if ctx.guild.voice_client is not None:
                await ctx.guild.voice_client.move_to(channel)
            else:
                await channel.connect(timeout=10.0)
            return True
        except asyncio.TimeoutError:
            send_func = ctx.send if hasattr(ctx, 'send') else ctx.channel.send
            await send_func(
                '❌ Could not connect to voice channel. '
                'Please check that I have permission to **Connect** and **Speak** in your voice channel.'
            )
            return False
        except discord.ClientException as e:
            send_func = ctx.send if hasattr(ctx, 'send') else ctx.channel.send
            await send_func(f'❌ Connection error: {str(e)}')
            return False
    
    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        """Handle reaction controls on now playing messages."""
        # Ignore bot's own reactions
        if user.bot:
            return
        
        # Check if this reaction is on a now playing message
        guild = reaction.message.guild
        if guild is None:
            return
        
        player = self.get_player(guild.id)
        if player.now_playing_message is None:
            return
        if reaction.message.id != player.now_playing_message.id:
            return
        
        voice_client = guild.voice_client
        emoji = str(reaction.emoji)
        
        # Remove user's reaction
        try:
            await reaction.remove(user)
        except discord.HTTPException:
            pass
        
        if emoji == EMOJI_PAUSE:
            if voice_client and voice_client.is_playing():
                voice_client.pause()
                await reaction.message.channel.send('⏸️ Paused', delete_after=3)
        
        elif emoji == EMOJI_RESUME:
            if voice_client and voice_client.is_paused():
                voice_client.resume()
                await reaction.message.channel.send('▶️ Resumed', delete_after=3)
            elif voice_client is None or not voice_client.is_connected():
                # Bot is not in channel, join and play current
                if await self.connect_to_voice(reaction.message, user):
                    if player.current:
                        await self.play_next(reaction.message)
                        await reaction.message.channel.send('▶️ Joining and resuming', delete_after=3)
                    else:
                        await reaction.message.channel.send('❌ Nothing to resume!', delete_after=3)
            else:
                await reaction.message.channel.send('❌ Nothing is paused!', delete_after=3)
        
        elif emoji == EMOJI_SKIP:
            if voice_client and voice_client.is_playing():
                voice_client.stop()  # Triggers play_next
                await reaction.message.channel.send('⏭️ Skipped', delete_after=3)
        
        elif emoji == EMOJI_STOP:
            if voice_client:
                player.clear()
                voice_client.stop()
                await reaction.message.channel.send('⏹️ Stopped', delete_after=3)
        
        elif emoji == EMOJI_QUEUE:
            # Show queue
            if not player.queue and not player.current:
                await reaction.message.channel.send('📭 Queue is empty!', delete_after=5)
            else:
                embed = discord.Embed(title='🎵 Music Queue', color=discord.Color.blurple())
                if player.current:
                    embed.add_field(name='Now Playing', value=f'**{player.current["title"]}**', inline=False)
                if player.queue:
                    queue_list = '\n'.join(f'{i+1}. {song["title"]}' for i, song in enumerate(list(player.queue)[:10]))
                    if len(player.queue) > 10:
                        queue_list += f'\n... and {len(player.queue) - 10} more'
                    embed.add_field(name='Up Next', value=queue_list, inline=False)
                await reaction.message.channel.send(embed=embed, delete_after=15)
        
        elif emoji == EMOJI_NINJA:
            # Play song #2 from local folder
            try:
                # Ensure joined first
                if voice_client is None or not voice_client.is_connected():
                    if not await self.connect_to_voice(reaction.message, user):
                        return
                    # Refresh voice_client after connecting
                    voice_client = guild.voice_client

                song = self.get_local_song_info(2)
                player.add(song)
                
                if voice_client and not voice_client.is_playing() and not voice_client.is_paused():
                    await reaction.message.channel.send('🥷 Playing **#2**', delete_after=3)
                    await self.play_next(reaction.message)
                else:
                    await reaction.message.channel.send('🥷 Added **#2** to queue', delete_after=3)
            except Exception as e:
                await reaction.message.channel.send(f'❌ {str(e)}', delete_after=5)
    
    @commands.hybrid_command(name='join', description='Join your voice channel')
    async def join(self, ctx: commands.Context):
        """Join the user's voice channel."""
        if await self.connect_to_voice(ctx):
            channel = ctx.author.voice.channel
            await ctx.send(f'✅ Joined **{channel.name}**')
    
    @commands.hybrid_command(name='leave', description='Leave the voice channel', aliases=['l', 'disconnect', 'dc'])
    async def leave(self, ctx: commands.Context):
        """Leave the voice channel."""
        if ctx.guild.voice_client is None:
            return await ctx.send('❌ I\'m not in a voice channel!')
        
        player = self.get_player(ctx.guild.id)
        player.clear()
        
        await ctx.guild.voice_client.disconnect()
        await ctx.send('👋 Disconnected from voice channel')
    
    @commands.hybrid_command(name='play', description='Play audio (number for local, text for YouTube)', aliases=['p'])
    @app_commands.describe(query='Song number (1-n) for local files, or YouTube URL/search text')
    async def play(self, ctx: commands.Context, *, query: str):
        """Play audio from local folder or YouTube.
        
        Examples:
        - !play 1          (plays first local song)
        - !play 5          (plays fifth local song)
        - !play https://youtube.com/watch?v=...
        - !play never gonna give you up
        """
        # Auto-join if not in voice channel
        if ctx.guild.voice_client is None:
            if not await self.connect_to_voice(ctx):
                return
        
        try:
            # Check if query is a number (local song)
            if query.isdigit():
                song_number = int(query)
                song = self.get_local_song_info(song_number)
                await ctx.send(f'📁 Playing **#{song_number}**')
            else:
                await ctx.send(f'🔍 Searching for: **{query}**')
                song = await self.extract_info(query)
        except Exception as e:
            return await ctx.send(f'❌ {str(e)}')
        
        player = self.get_player(ctx.guild.id)
        player.add(song)
        
        # If not currently playing, start playing
        voice_client = ctx.guild.voice_client
        if voice_client and not voice_client.is_playing() and not voice_client.is_paused():
            await self.play_next(ctx)
        else:
            await ctx.send(f'📝 Added to queue: **{song["title"]}**')
    
    @commands.hybrid_command(name='songs', description='Show number of available local songs', aliases=['list', 'local'])
    async def songs(self, ctx: commands.Context):
        """Show the number of available local songs."""
        songs = get_local_songs()
        
        if not songs:
            return await ctx.send('📭 No audio files found')
        
        await ctx.send(f'📁 **{len(songs)}** songs available. Use `/play 1` to `/play {len(songs)}` to play.')
    
    @commands.hybrid_command(name='pause', description='Pause the current song')
    async def pause(self, ctx: commands.Context):
        """Pause the current song."""
        voice_client = ctx.guild.voice_client
        if voice_client is None or not voice_client.is_playing():
            return await ctx.send('❌ Nothing is playing!')
        
        voice_client.pause()
        await ctx.send('⏸️ Paused')
    
    @commands.hybrid_command(name='resume', description='Resume playback', aliases=['unpause'])
    async def resume(self, ctx: commands.Context):
        """Resume the paused song."""
        voice_client = ctx.guild.voice_client
        
        if voice_client and voice_client.is_paused():
            voice_client.resume()
            await ctx.send('▶️ Resumed')
        elif voice_client is None or not voice_client.is_connected():
            # Bot is not in channel, join and play current
            if await self.connect_to_voice(ctx):
                player = self.get_player(ctx.guild.id)
                if player.current:
                    await self.play_next(ctx)
                    await ctx.send('▶️ Joining and resuming')
                else:
                    await ctx.send('❌ Nothing to resume!')
        else:
            await ctx.send('❌ Nothing is paused!')
    
    @commands.hybrid_command(name='stop', description='Stop playback and clear queue')
    async def stop(self, ctx: commands.Context):
        """Stop playback and clear the queue."""
        if ctx.guild.voice_client is None:
            return await ctx.send('❌ I\'m not in a voice channel!')
        
        player = self.get_player(ctx.guild.id)
        player.clear()
        
        ctx.guild.voice_client.stop()
        await ctx.send('⏹️ Stopped and cleared the queue')
    
    @commands.hybrid_command(name='skip', description='Skip the current song', aliases=['s', 'next'])
    async def skip(self, ctx: commands.Context):
        """Skip the current song."""
        voice_client = ctx.guild.voice_client
        if voice_client is None or not voice_client.is_playing():
            return await ctx.send('❌ Nothing is playing!')
        
        voice_client.stop()  # This will trigger after callback -> play_next
        await ctx.send('⏭️ Skipped')
    
    @commands.hybrid_command(name='queue', description='Show the current queue', aliases=['q'])
    async def queue(self, ctx: commands.Context):
        """Show the current queue."""
        player = self.get_player(ctx.guild.id)
        
        if not player.queue and not player.current:
            return await ctx.send('📭 Queue is empty!')
        
        embed = discord.Embed(title='🎵 Music Queue', color=discord.Color.blurple())
        
        if player.current:
            source = '📁' if player.current.get('is_local') else '🌐'
            embed.add_field(
                name='Now Playing',
                value=f'{source} **{player.current["title"]}**',
                inline=False
            )
        
        if player.queue:
            queue_list = '\n'.join(
                f'{i+1}. {"📁" if song.get("is_local") else "🌐"} {song["title"]}'
                for i, song in enumerate(list(player.queue)[:10])
            )
            remaining = len(player.queue) - 10
            if remaining > 0:
                queue_list += f'\n... and {remaining} more'
            embed.add_field(name='Up Next', value=queue_list, inline=False)
        
        embed.set_footer(text=f'Total in queue: {len(player.queue)} song(s)')
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='nowplaying', description='Show the current song', aliases=['np', 'current'])
    async def nowplaying(self, ctx: commands.Context):
        """Show the currently playing song."""
        player = self.get_player(ctx.guild.id)
        
        if not player.current:
            return await ctx.send('❌ Nothing is playing!')
        
        await self.send_now_playing(ctx, player.current)
    
    @commands.hybrid_command(name='loop', description='Toggle loop mode')
    async def loop(self, ctx: commands.Context):
        """Toggle loop mode for the current song."""
        player = self.get_player(ctx.guild.id)
        player.loop = not player.loop
        
        status = '🔁 Loop enabled' if player.loop else '➡️ Loop disabled'
        await ctx.send(status)


async def setup(bot):
    await bot.add_cog(Music(bot))
