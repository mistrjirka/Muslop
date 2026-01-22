import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import yt_dlp
from collections import deque


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

# Control emojis
EMOJI_PAUSE = '⏸️'
EMOJI_RESUME = '▶️'
EMOJI_SKIP = '⏭️'
EMOJI_STOP = '⏹️'
EMOJI_QUEUE = '📜'
CONTROL_EMOJIS = [EMOJI_PAUSE, EMOJI_RESUME, EMOJI_SKIP, EMOJI_STOP, EMOJI_QUEUE]


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
                }
            except Exception as e:
                raise Exception(f'Failed to extract audio: {str(e)}')
    
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
        
        if song.get('duration'):
            minutes, seconds = divmod(song['duration'], 60)
            embed.add_field(name='Duration', value=f'{minutes}:{seconds:02d}')
        
        # Add control instructions
        embed.set_footer(text='⏸️ Pause | ▶️ Resume | ⏭️ Skip | ⏹️ Stop | 📜 Queue')
        
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
        
        source = discord.FFmpegPCMAudio(song['url'], **FFMPEG_OPTIONS)
        
        def after_playing(error):
            if error:
                print(f'Player error: {error}')
            # Schedule next song
            asyncio.run_coroutine_threadsafe(self.play_next(ctx), self.bot.loop)
        
        voice_client.play(source, after=after_playing)
        
        # Send now playing with controls
        await self.send_now_playing(ctx, song)
    
    async def connect_to_voice(self, ctx) -> bool:
        """Try to connect to voice channel with error handling."""
        if ctx.author.voice is None:
            await ctx.send('❌ You must be in a voice channel!')
            return False
        
        channel = ctx.author.voice.channel
        
        try:
            if ctx.guild.voice_client is not None:
                await ctx.guild.voice_client.move_to(channel)
            else:
                await channel.connect(timeout=10.0)
            return True
        except asyncio.TimeoutError:
            await ctx.send(
                '❌ Could not connect to voice channel. '
                'Please check that I have permission to **Connect** and **Speak** in your voice channel.'
            )
            return False
        except discord.ClientException as e:
            await ctx.send(f'❌ Connection error: {str(e)}')
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
    
    @commands.hybrid_command(name='play', description='Play audio from YouTube (URL or search)', aliases=['p'])
    @app_commands.describe(query='YouTube URL or search text (e.g., "never gonna give you up")')
    async def play(self, ctx: commands.Context, *, query: str):
        """Play audio from a YouTube URL or search query.
        
        Examples:
        - !play https://youtube.com/watch?v=...
        - !play never gonna give you up
        - /play despacito
        """
        # Auto-join if not in voice channel
        if ctx.guild.voice_client is None:
            if not await self.connect_to_voice(ctx):
                return
        
        await ctx.send(f'🔍 Searching for: **{query}**')
        
        try:
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
        if voice_client is None or not voice_client.is_paused():
            return await ctx.send('❌ Nothing is paused!')
        
        voice_client.resume()
        await ctx.send('▶️ Resumed')
    
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
            embed.add_field(
                name='Now Playing',
                value=f'**{player.current["title"]}**',
                inline=False
            )
        
        if player.queue:
            queue_list = '\n'.join(
                f'{i+1}. {song["title"]}'
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
