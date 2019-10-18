from discord.ext import tasks, commands
from twitch import TwitchClient

import discord
import datetime
import asyncio
import json
import logging

import config

f_json = "twitch_channels.json"

poll_delay = 15*60

class Twitch(commands.Cog):
    """Bot utilities for twitch integration."""

    global logger
    logger = logging.getLogger("bot")

    def __init__(self, bot):
        self.bot = bot
        self.channels = []
        self.active_streams = []

        self.notification_reciever = None

        self.twitch = TwitchClient(client_id=config.twitch_client_id)
        self.poll_channels.start()

    def cog_unload(self):
        self.poll_channels.cancel()
        logger.info(f"Unloading Twitch poll module")

    @commands.group()
    async def twitch(self, ctx):
        if ctx.invoked_subcommand is None:
            try:
                embed = discord.Embed(colour=0x000000, title=f'Twitch kanavat')
                embed.add_field(name = 'Lista',
                            value = f"Lista seuratuista kanavista: ?twitch lista\n",
                            inline = True)
                await ctx.send(embed = embed)
            except discord.Forbidden:
                await ctx.send("Ei oikeuksia.")

    @twitch.group(name="lista", aliases=['list'])
    async def dispaly_follow_list(self, ctx):
        """List channels we are following"""
        for c_id in self.channels:
            channel = self.twitch.channels.get_by_id(c_id)
            embed = discord.Embed(colour=0x00FF00,
                    title = channel.display_name,
                    url = channel.url,
                    description = f"{channel.status}\nSeuraajia: {channel.followers}",)
            embed.set_thumbnail(url = channel.logo)
            await ctx.send(embed = embed)

    @twitch.group(name="video")
    async def dispaly_channel_videos(self, ctx, name: str):
        """List latest videos in channel by channel name"""
        try:
            search = name.split("/")[-1:] #Jos url, otetaan lopusta kanavan nimi
            users = self.twitch.users.translate_usernames_to_ids(search)
            if len(users) == 1:
                videos = self.twitch.channels.get_videos(users[0].id, limit=5, broadcast_type='archive,upload')
                if videos:
                    embed = discord.Embed(colour=0x00FF00,
                            title = f"{videos[0].channel.display_name}",
                            url = f"{videos[0].channel.url}")
                    for v in videos:
                        embed.add_field(name = f"{v.title}",
                                value = f"{v.url}",
                                inline = True)
                    await ctx.send(embed = embed)
                else:
                    await ctx.send(f"Videoita ei löytynyt kanavalta {search}")
            else:
                await ctx.send(f"Haulla {search} löytyi {len(users)} kanavaa.\n{[u for u in users]}")
        except Exception as e:
            logger.warning(f"Error on twitch video: {e}")

    @twitch.group(name="lisaa", aliases=['add'])
    async def add_channel_to_list(self, ctx, name: str):
        """Add channel to follow list by channel name"""
        try:
            search = name.split("/")[-1:] #Jos url, otetaan lopusta kanavan nimi
            users = self.twitch.users.translate_usernames_to_ids(search)

            if len(users) == 1:
                if users[0].id in self.channels:
                    await ctx.send("Kanava on jo listalla")
                else:
                    self.channels.append(users[0].id)
                    self.save_channels()

                    embed = discord.Embed(colour=0xFF0000,
                            title = f"Lisätään: {users[0].display_name}",
                            url = f"https://www.twitch.tv/{users[0].name}",
                            description = f"{users[0].bio}",)
                    embed.set_thumbnail(url = users[0].logo)
                    await ctx.send(embed = embed)
                    logger.info(f"Käyttäjä {ctx.author.display_name} (Käyttäjän ID: {ctx.author.id}) lisäsi kanavan: {users[0].name} (ID:{users[0].id})")
            else:
                await ctx.send(f"Haulla {search} löytyi {len(users)} käyttäjää.\n{[u for u in users]}")
        except Exception as e:
            logger.warning(f"Error on twitch lisaa: {e}")
            await ctx.send(f"Kanavan lisääminen ei onnistunut")

    @twitch.group(name="poista", aliases=['remove'])
    async def remove_from_list(self, ctx, name: str):
        """Remove a channel from following list by channel name"""
        try:
            search = name.split("/")[-1:] #Jos url, otetaan lopusta kanavan nimi
            users = self.twitch.users.translate_usernames_to_ids(search)

            if len(users) == 1:
                if users[0].id in self.channels:
                    embed = discord.Embed(colour=0xFF0000,
                            title = f"Poistetaan: {users[0].display_name}",
                            url = f"https://www.twitch.tv/{users[0].name}",
                            description = f"{users[0].bio}",)
                    embed.set_thumbnail(url = users[0].logo)
                    await ctx.send(embed = embed)
                    logger.info(f"Käyttäjä {ctx.author.display_name} (Käyttäjän ID: {ctx.author.id}) poisti kanavan: {users[0].name} (ID:{users[0].id})")

                    self.channels.remove(users[0].id)
                    self.save_channels()
                else:
                    await ctx.send("Kanava ei löytynyt listalta")
            else:
                await ctx.send(f"Haulla {search} löytyi {len(users)} käyttäjää.\n{[u for u in users]}")
        except Exception as e:
            logger.warning(f"Error on twitch lisaa: {e}")
            await ctx.send(f"Kanavan poistaminen ei onnistunut")


    def save_channels(self):
        with open(f_json, 'w') as fp:
            json.dump(self.channels, fp, indent=4)
        logger.info(f"Tallennettu {len(self.channels)} kanavaa")

    def load_channels(self):
        try:
            with open(f_json, 'r') as fp:
                self.channels = json.load(fp)
        except:
            self.channels = []
        logger.info(f"Ladattu {len(self.channels)} kanavaa\n{self.channels}")


    async def poll_new_videos(self):
        global poll_delay
        time = datetime.datetime.now().replace(microsecond=0) - datetime.timedelta(seconds=poll_delay)
        logger.info(f"Tarkistetaan viimeisimpiä Twitch videoita...")
        for cid in self.channels:
            try:
                videos = self.twitch.channels.get_videos(cid, limit=1, broadcast_type='archive,upload')
                if videos and videos[0]['published_at'] > time:
                    embed = discord.Embed(colour=0x0000FF,
                            title = f"Video: {videos[0].channel.display_name}",
                            url = videos[0].url,
                            description = f"{videos[0].title}\nat: {videos[0].game}",)
                    embed.set_thumbnail(url = videos[0].channel.logo)
                    await self.notification_reciever.send(embed=embed)
            except Exception as e:
                logger.warning(f"Error on twitch poll videos: {e}")

    async def poll_active_streams(self):
        if len(self.channels):
            streams = self.twitch.streams.get_live_streams(self.channels, limit=100)
        else:
            streams = []

        new_active = []
        for stream in streams:
            new_active.append(stream.id)
            if stream.id not in self.active_streams:
                embed = discord.Embed(colour=0xFF0000,
                        title = f"Stream: {stream.channel.display_name}",
                        url = stream.channel.url,
                        description = f"{stream.channel.status}\nat: {stream.channel.game}",)
                embed.set_thumbnail(url = stream.channel.logo)
                await self.notification_reciever.send(embed=embed)
        self.active_streams = new_active.copy()
        logger.info(f"Tarkistetaan aktiivisia Twitch streameja: {[s.channel.display_name for s in streams]}")

    @tasks.loop(seconds = poll_delay)
    async def poll_channels(self):
        if self.notification_reciever:
            await self.poll_active_streams()
            await self.poll_new_videos()
        else:
            logger.info(f"Twitch poll module not yet fully loaded or no channel to post to")

    @poll_channels.before_loop
    async def before_poll_channels(self):
        await self.bot.wait_until_ready()
        self.load_channels()
        logger.info(f"Preloading Twitch poll module")
        if config.channel_to_post:
            self.notification_reciever = self.bot.get_channel(config.channel_to_post)


def setup(bot):
    bot.add_cog(Twitch(bot))
