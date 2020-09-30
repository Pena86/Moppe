from discord.ext import tasks, commands
from library.common import checks
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from pprint import pprint

import discord
import gspread
import datetime
import asyncio
import json
import logging
import pickle
import toml
import re

import config

FOLDER = "report/"
MEMBER_NICKS_FILE = FOLDER + "member_nicks.toml"
MEMBER_ROLES_FILE = FOLDER + "member_roles.toml"

class Messages(commands.Cog):
    """Actions taken based on server messages, that are not commands"""

    global logger
    logger = logging.getLogger("bot")

    def __init__(self, bot):
        self.bot = bot

        self.member_nicks = {} # {'member': [nick, ...], ...}
        self.read_member_nicks() # Read from a file

        self.automation_channel = None
        if hasattr(config, 'automation_channel_id'):
            guild = discord.utils.get(self.bot.guilds, id=config.guild_id)
            try:
                self.automation_channel = discord.utils.get(guild.text_channels, id=config.automation_channel_id)
            except AttributeError:
                if not guild:
                    print("ERROR: Invalid guild id in config\n")
                else:
                    print("ERROR: Invalid channel id in config\n")
                raise

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """on_member_join actions
        send join message
        """
        if False:
            logger.info(f"Servulle liittyjälle lähetetty kutsuviesti: {member.display_name} "
                        f"(ID: {member.id}).")
            # member_nina = self.bot.get_user(222394927978381312) {member_nina.mention}
            member_ebot = self.bot.get_user(config.bot_own_user_id)

            join_message = f"""
Mukavaa että olet löytänyt tiesi **Messis** -yhteisön Discord servulle!
Vielä yksi askel, niin pääset keskustelemaan muiden seuraan! :blush:

Tee itsestäsi lyhyt **esittely**, joka toimii hakemuskena. Voit kertoa kiinnostuksen kohteista, harrastuksista, miten löysit Messiksen, asioista jotka ovat sinulle tärkeitä tms.
Lähetä esittely **@Nina** 'lle yksityisviestillä tai vastaa tähän {member_ebot.mention} 'lle, niin välitän esittelyn **@Staff** 'in käsiteltäväksi.
Esittelyssä kerrottuja tietoja ei jaeta @Staff 'in ulkopuolelle.

Hakemuksesi käsitellään parin päivän sisällä. Hyväksytyn hakemuksen jälkeen saat täydet keskusteluoikeudet servulle. Muussa tapauksessa olemme yhteydessä sinuun.

Tervetuloa! :fire: T. **Messis @Staff**

ps. Tällä hakemusmenettelyllä pyrimme ehkäisemään botti/trolli käyttäjiä ja pitämään yhteisömme mukavana paikkana kaikille jäsenille.
Hyväksynnän jälkeen voit halutessasi postata esittelysi myös muiden yhteisöläisten nähtäville **#👤esittelyt** kanavalle
                """

            await member.send(join_message)

    @commands.Cog.listener()
    async def on_message(self, message):
        """on_message actions
        invite functionality
        """
        # pprint(dir(message))
        # print(message.created_at, message.type, message.author, message.channel, message.guild)

        if message.type == discord.MessageType.default:
            if message.self.guild == None:
                # Private messages
                # print(message.author.id, self.guild.get_member(message.author.id))
                member = self.guild.get_member(message.author.id)
                if member:
                    # is a member
                    # print("IS member")
                    # print(member.roles)
                    if len(member.roles) > 1:
                        #print("has roles")
                        pass
                    else:
                        # print("no roles")
                        # await self.deliver_request(message) # Invite message disabled
                        pass
                else:
                    # not a member
                    pass
            else:
                # channel messages
                pass
        else:
            # other type messages
            pass


    async def deliver_request(self, message):
        """We assume, that a user, who is in server, but has no roles, and sends pm to bot, that that pm is join request
        Send it to the channel for processing
        """
        logger.info(f"Servulle liittyjän kutsuviesti toimitettu hakemuksiin: {message.author.display_name} "
                    f"(ID: {message.author.id}).")

        channel = discord.utils.get(self.guild.text_channels, id=config.join_request_channel_id)
        staff_role = self.guild.get_role(config.staff_role_id)

        msg = await channel.send(f"{staff_role.mention} User {message.author.mention} sent a possible join request:", embed=discord.Embed(colour=0x000000, description=message.content))
        reactions = ['✅', '🔶', '⛔', '🆗']
        for emoji in reactions:
            await msg.add_reaction(emoji)
        #await sender.send(f"Your application has been delivered")
        await message.author.send(f"Liittymispyyntösi on välitetty Staffin käsiteltäväksi. He ovat yhteydessä pikimmiten :)")

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        """Listen for message reacts
        Does not get triggered when other users join reaction
        """

        #pprint(reaction)
        #pprint(user)

        #print(reaction, user.name, user.guild, reaction.count)#, reaction.message)


    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.channel_id == config.join_request_channel_id:
            if isinstance(payload.emoji, str):
                reaction_name = payload.emoji
                reaction_id = None
            else:
                reaction_name = payload.emoji.name
                reaction_id = payload.emoji.id
            if reaction_name == '✅':
                #get the message data
                channel = discord.utils.get(self.guild.text_channels, id=config.join_request_channel_id)
                message = await channel.fetch_message(payload.message_id)
                #print(message, message.reactions)

                #if '✅' in message.reactions:
                for r in message.reactions:
                    if isinstance(r.emoji, str) and r.emoji == '✅' and r.count == 4:
                        #print(message.clean_content)
                        #print(message.system_content)
                        #print(message.content)
                        ids = re.findall(r'\d+', message.system_content)
                        #print(ids[1])
                        sender = discord.utils.get(self.guild.members, id=int(ids[1]))
                        #print(sender)
                        role = discord.utils.get(self.guild.roles, name="ihminen")
                        #print(role)

                        await sender.add_roles(role, reason="joinrequest", atomic=True)
                        msg = await channel.send(f"User {sender.mention} was given role {role}")
                        channel = discord.utils.get(self.guild.text_channels, id=config.common_welcome_channel)
                        msg = await channel.send(f"Tervetuloa Messikseen {sender.mention}!")
                        print(f"User {sender.mention} was given role {role} and sent a welcome message")

                        break

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        """Listen for member updates (status, activity, nickname, roles)
        """

        #pprint(before)
        #pprint(after)

        #print(f"{after.name} {after.status} {after.activity} {after.nick} {after.roles}")

        #if before.activity != after.activity:
        #    print(f"{after.name} {before.activity} --> {after.activity}")

        if before.nick != after.nick:
            #print(f"{after.name} {before.nick} --> {after.nick}")
            if after.nick != None:
                if str(after) not in self.member_nicks:
                    self.member_nicks[str(after)] = [str(after.nick)]
                else:
                    self.member_nicks[str(after)].append(str(after.nick))
                #print(f"{after.name} changed nick to {after.nick}.\nAll known nicks are: {', '.join(self.member_nicks[str(after)])}")
            else:
                if str(after) not in self.member_nicks:
                    self.member_nicks[str(after)] = [str(before.nick)]
                #print(f"{after.name} removed nick.\nAll known nicks are: {', '.join(self.member_nicks[str(after)])}")
            if self.automation_channel:
                await self.automation_channel.send(f"{after.mention} muutti / poisti nickinsä. Kaikki hänen käyttämät nickit ovat:\n{', '.join(self.member_nicks[str(after)])}")
            self.write_member_nicks()

        if before.roles != after.roles:
            #print(f"{after.name} {before.roles} --> {after.roles}")
            if len(before.roles) > len(after.roles):
                print(f"{datetime.datetime.now()} {after.name} role removed, left with: {after.roles}")
            elif len(before.roles) < len(after.roles):
                #print("Role added")
                for r in after.roles:
                    if r not in before.roles:
                        #print(r)
                        print(f"{datetime.datetime.now()} {after.name} {r} role added, total: {after.roles}")
                        with open(MEMBER_ROLES_FILE, mode='a+') as f:
                            f.write(str(datetime.datetime.now()) + "|" + str(after.name) + "|" + str(r.name) + "\n")


    def write_member_nicks(self):
        """Writes self.member_nicks to a file
        """
        with open(MEMBER_NICKS_FILE, mode='w') as w:
            w.writelines(toml.dumps(self.member_nicks))

    def read_member_nicks(self):
        """Reads self.member_nicks from a file
        """
        with open(MEMBER_NICKS_FILE, 'r') as f:
            self.member_nicks = toml.loads(f.read())


def setup(bot):
    bot.add_cog(Messages(bot))
