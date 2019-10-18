from discord.ext import tasks, commands
from googleapiclient.discovery import build

import discord
import datetime
import asyncio
import json
import logging

import config

# https://developers.google.com/apis-explorer/?hl=en_GB#p/youtube/v3/
# https://github.com/youtube/api-samples

f_json = "youtube_channels.json"

API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'

poll_delay = 15 * 60


class Youtube(commands.Cog):
    """Bot utilities for youtube integration."""

    global logger
    logger = logging.getLogger("bot")

    def __init__(self, bot):
        self.bot = bot
        self.channels = []
        self.active_streams = []

        self.notification_reciever = None

        self.youtube = build(API_SERVICE_NAME, API_VERSION, developerKey=config.youtube_api_key)
        self.poll_channels.start()

    def cog_unload(self):
        self.poll_channels.cancel()
        logger.info(f"Unloading youtube poll module")

    async def channel_name_to_id(self, ctx, name: str):
        """Helper function to get youtube channel snippet by name"""
        request = self.youtube.search().list(
            part="snippet",
            maxResults=9,
            q=name,
            safeSearch="moderate",
            type="channel"
        )
        response = request.execute()
        match = False
        for c in response.get('items', []):
            if c['snippet']['title'] == name:
                match = c
                break

        if match == False:
            embed = discord.Embed(colour=0xFF0000,
                                  title=f"Search results:")
            for c in response.get('items', []):
                embed.add_field(name=f"{c['snippet']['title']}",
                                value=f"{c['snippet']['description']}\nhttps://www.youtube.com/channel/{c['id']['channelId']}",
                                inline=True)
            await ctx.send(embed=embed)
        return match

    @commands.group()
    async def youtube(self, ctx):
        if ctx.invoked_subcommand is None:
            try:
                embed = discord.Embed(colour=0x000000, title=f'youtube kanavat')
                embed.add_field(name='Lista',
                                value=f"Lista seuratuista kanavista: ?youtube lista\n",
                                inline=True)
                await ctx.send(embed=embed)
            except discord.Forbidden:
                await ctx.send("Ei oikeuksia.")

    @youtube.group(name="lista", aliases=['list'])
    async def dispaly_follow_list(self, ctx):
        """List channels we are following"""
        for chan in self.channels:
            request = self.youtube.channels().list(
                part="snippet",
                id=chan[0]
            )
            response = request.execute()
            if 'items' in response and len(response['items']) > 0:
                channel = response.get('items', [])[0]
                embed = discord.Embed(colour=0x00FF00,
                                      title=channel['snippet']['title'],
                                      url=f"https://www.youtube.com/watch?v={channel['id']}",
                                      description=channel['snippet']['description'], )
                embed.set_thumbnail(url=channel['snippet']['thumbnails']['default']['url'])
                await ctx.send(embed=embed)

    @youtube.group(name="video")
    async def dispaly_channel_videos(self, ctx, name: str):
        """List latest videos in channel by channel name
        If searc string contains whitespace, put it inside quotes"""
        try:
            search = await self.channel_name_to_id(ctx, name)
            if search == False:
                return False
            request = self.youtube.search().list(
                part="snippet",
                channelId=search['id']['channelId'],
                maxResults=3,
                order="date",
            )
            response = request.execute()

            if len(response['items']) > 0:
                embed = discord.Embed(colour=0x00FF00,
                                      title=f"{response['items'][0]['snippet']['channelTitle']}",
                                      url=f"https://www.youtube.com/channel/{response['items'][0]['snippet']['channelId']}")
                for video in response.get('items', []):
                    embed.add_field(name=f"{video['snippet']['title']}",
                                    value=f"https://www.youtube.com/watch?v={video['id']['videoId']}",
                                    inline=True)
                await ctx.send(embed=embed)
            else:
                await ctx.send(f"Videoita ei löytynyt kanavalta {search}")
        except Exception as e:
            await ctx.send(f"Haulla {search['snippet']['title']} ei löytynyt kanavia")
            logger.warning(f"Error on youtube video: {e}")

    @youtube.group(name="lisaa", aliases=['add'])
    async def add_channel_to_list(self, ctx, name: str):
        """Add channel to follow list by channel name"""
        try:
            user = await self.channel_name_to_id(ctx, name)
            if user:
                if user['id']['channelId'] in [chan[0] for chan in self.channels]:
                    await ctx.send("Kanava on jo listalla")
                else:
                    self.channels.append((user['id']['channelId'], user['snippet']['title']))
                    self.save_channels()

                    embed = discord.Embed(colour=0xFF0000,
                                          title=f"Lisätään: {user['snippet']['title']}",
                                          url=f"https://www.youtube.tv/{user['id']['channelId']}",
                                          description=user['snippet']['description'], )
                    embed.set_thumbnail(url=user['snippet']['thumbnails']['default']['url'])
                    await ctx.send(embed=embed)
                    logger.info(
                        f"Käyttäjä {ctx.author.display_name} (Käyttäjän ID: {ctx.author.id}) lisäsi kanavan: {user['snippet']['title']} (ID:{user['id']['channelId']})")
        except Exception as e:
            logger.warning(f"Error on youtube lisaa: {e}")
            await ctx.send(f"Kanavan lisääminen ei onnistunut")

    @youtube.group(name="poista", aliases=['remove'])
    async def remove_from_list(self, ctx, name: str):
        """Remove a channel from following list by channel name"""
        try:
            user = await self.channel_name_to_id(ctx, name)
            if user and user['id']['channelId'] in [chan[0] for chan in self.channels]:
                embed = discord.Embed(colour=0xFF0000,
                                      title=f"Poistetaan: {user['snippet']['title']}",
                                      url=f"https://www.youtube.tv/{user['id']['channelId']}",
                                      description=user['snippet']['description'], )
                embed.set_thumbnail(url=user['snippet']['thumbnails']['default']['url'])
                await ctx.send(embed=embed)
                logger.info(
                    f"Käyttäjä {ctx.author.display_name} (Käyttäjän ID: {ctx.author.id}) poisti kanavan: {user['snippet']['title']} (ID:{user['id']['channelId']})")

                self.channels.remove((user['id']['channelId'], user['snippet']['title']))
                self.save_channels()
            elif user:
                await ctx.send("Kanava ei löytynyt listalta")
        except Exception as e:
            logger.warning(f"Error on youtube lisaa: {e}")
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
        logger.info(f"Tarkistetaan viimeisimpiä youtube videoita...")
        for cid, cname in self.channels:
            try:
                request = self.youtube.search().list(
                    part="snippet",
                    channelId=cid,
                    maxResults=1,
                    order="date",
                )
                response = request.execute()
                if len(response['items']) > 0 and datetime.datetime.strptime(response['items'][0]['snippet']['publishedAt'], "%Y-%m-%dT%H:%M:%S.%fZ") > time:
                    embed = discord.Embed(colour=0x0000FF,
                            title=f"Video: {response['items'][0]['snippet']['channelTitle']}",
                            url=f"https://www.youtube.com/channel/{response['items'][0]['snippet']['channelId']}",
                            description=response['items'][0]['snippet']['description'])
                    embed.set_thumbnail(url=response['items'][0]['snippet']['thumbnails']['default']['url'])
                    await self.notification_reciever.send(embed=embed)
            except Exception as e:
                logger.warning(f"Error on youtube poll videos: {e}")

    @tasks.loop(seconds = poll_delay)
    async def poll_channels(self):
        if self.notification_reciever:
            await self.poll_new_videos()
        else:
            logger.info(f"youtube poll module not yet fully loaded or no channel to post to")

    @poll_channels.before_loop
    async def before_poll_channels(self):
        await self.bot.wait_until_ready()
        self.load_channels()
        logger.info(f"Preloading youtube poll module")
        if config.channel_to_post:
            self.notification_reciever = self.bot.get_channel(config.channel_to_post)


def setup(bot):
    bot.add_cog(Youtube(bot))
