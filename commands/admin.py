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

    @commands.command(hidden=True)
    #@checks.am_i_owner()
    async def reload(self, ctx, ext: str):
        """Restart given extension if found"""
        try:
            extension = 'commands.' + ext
            self.bot.reload_extension(extension)
            logger.info(f"Reloaded extension: {extension}. Komennon suorittaja: {ctx.author.display_name} "
                        f"(ID: {ctx.author.id}).")
            await ctx.author.send(f"Reloaded extension: {extension}")
        except Exception as e:
            error_message = f"Error on reloading extension: {e}"
            logger.warning(error_message)
            await ctx.author.send(error_message)


def setup(bot):
    bot.add_cog(Admin(bot))
