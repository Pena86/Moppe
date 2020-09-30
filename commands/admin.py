from discord.ext import commands
import discord
import logging
from library.common import checks


class Admin(commands.Cog):
    """Admin commands for bot management"""
    global logger
    logger = logging.getLogger("bot")

    def __init__(self, bot):
        self.bot = bot
        self.ext = None

    @commands.command(hidden=True)
    #@checks.am_i_owner()
    async def reload(self, ctx, ext: str):
        """Restart given extension if found"""
        try:
            extension = 'commands.' + ext
            self.bot.reload_extension(extension)
            self.ext = extension
            #load_extension() https://discordpy.readthedocs.io/en/latest/ext/commands/api.html
            logger.info(f"Reloaded extension: {extension}. Komennon suorittaja: {ctx.author.display_name} "
                        f"(ID: {ctx.author.id}).")
            #await ctx.author.send(f"Reloaded extension: {extension}")
            await ctx.send(f"Reloaded extension: {extension}")
        except Exception as e:
            self.ext = None
            error_message = f"Error on reloading extension: {e}"
            logger.warning(error_message)
            #await ctx.author.send(error_message) # DM
            await ctx.send(error_message) # to channel

    @commands.command(hidden=True)
    #@checks.am_i_owner()
    async def re(self, ctx):
        """Restart last reloaded extension if found"""
        print("test", self.ext)
        try:
            self.bot.reload_extension(self.ext)
            #load_extension() https://discordpy.readthedocs.io/en/latest/ext/commands/api.html
            logger.info(f"Reloaded extension: {self.ext}. Komennon suorittaja: {ctx.author.display_name} "
                        f"(ID: {ctx.author.id}).")
            #await ctx.author.send(f"Reloaded extension: {extension}")
            await ctx.send(f"Reloaded extension: {self.ext}")
        except Exception as e:
            error_message = f"Error on reloading extension: {e}"
            logger.warning(error_message)
            #await ctx.author.send(error_message)
            await ctx.send(error_message)


def setup(bot):
    bot.add_cog(Admin(bot))
