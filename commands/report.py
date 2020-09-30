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

import config

FOLDER = "report/"
CHANNELS_FILE = FOLDER + "channels_file.pickle"
MESSAGES_FILE = FOLDER + "messages_file.pickle"
REPORT_FILE = FOLDER + "report_file" #dates and '.txt' added
HEADERS_FILE = FOLDER + "headers_file.txt"

VIIKONPAIVA = {
    'Monday': 'Maanantai',
    'Tuesday': 'Tiistai',
    'Wednesday': 'Keskiviikko',
    'Thursday': 'Torstai',
    'Friday': 'Perjantai',
    'Saturday': 'Lauantai',
    'Sunday': 'Sunnuntai',
}

testrun = False
#testrun = True # Enable testrun when developing

class Report(commands.Cog):
    """Viikkoraportin generointi discordista google sheetsiin"""

    global logger
    logger = logging.getLogger("bot")

    def __init__(self, bot):
        self.bot = bot
        self.mode = None
        self.message_handle = None

    @commands.group(name="raportti", aliases=["rep"], hidden=True)
    #@checks.is_staff()
    async def rep(self, ctx):
        """Messis viikkoraportti"""
        self.mode = None
        logger.info(f"Viikkoraportin generointi. Komennon suorittaja: {ctx.author.display_name} "
                    f"(ID: {ctx.author.id}).")
        if ctx.invoked_subcommand is None:
            r = self.bot.get_cog("Report")
            #await r.list_all_channels.invoke(ctx)
            await r.report_all_channels.invoke(ctx)
            await r.create_report.invoke(ctx)
            if not testrun:
                await r.upload_report_g_sheets.invoke(ctx)

    @commands.group(name="top20", aliases=["top"], hidden=True)
    #@checks.is_staff()
    async def top(self, ctx):
        self.mode = "top20"
        """Messis top20 käyttäjät, jotka ei ole vaikuttajia"""
        logger.info(f"Top20 käyttäjät generointi. Komennon suorittaja: {ctx.author.display_name} "
                    f"(ID: {ctx.author.id}).")
        if ctx.invoked_subcommand is None:
            r = self.bot.get_cog("Report")
            #await r.list_all_channels.invoke(ctx)
            await r.report_all_channels.invoke(ctx)
            await r.create_report.invoke(ctx)
            #if not testrun:
            #    await r.upload_report_g_sheets.invoke(ctx)


    @rep.group(name="l", aliases=["1"], hidden=True)
    #@checks.is_staff()
    async def list_all_channels(self, ctx):
        """Get channels to report
        function not in use atm"""
        await ctx.send(f"Viikkoraportti 1/3\nHaetaan lista kanavista palvelimella")

        channel_category = []
        channel_no_premission = []
        channel_to_report = []
        channel_ignored = []

        guild = discord.utils.get(self.bot.guilds, id=config.guild_id)
        #print (dir(guild.me))
        #print (guild.me.history)
        pprint(guild.categories)
        for channel in guild.channels:
            #if "info" in channel.name:
            #    pprint(channel)
            #print (channel.guild, channel.category_id, channel.category, channel.type,
            #        channel.id, channel.name, channel.permissions_for(guild.me).value)
            if str(channel.type) == "text" and channel.category_id:
                if channel.permissions_for(guild.me).value > 0:
                    if not channel.id in config.ignored_channels:
                        channel_to_report.append(channel)
                    else:
                        channel_ignored.append(channel)
                else:
                    channel_no_premission.append(channel)
            else:
                channel_category.append(channel)

        #print (len(channel_to_report), len(channel_no_premission), "\n###To report")

        channel_to_report.sort(key=lambda elem: elem.category_id)
        to_pickled = []
        for channel in channel_to_report:
            #print (channel.category_id, channel.category, channel.id, channel.name)
            to_pickled.append((int(channel.id), str(channel.name), int(channel.category_id), str(channel.category)))

        #print(len(to_pickled), type(to_pickled))

        #pickle.dump( to_pickled, open( CHANNELS_FILE, "wb" ) )

        """
        print("\n\n###Ignored:")
        for channel in channel_ignored:
            print (channel.guild, channel.category_id, channel.category, channel.type,
                    channel.id, channel.name, channel.permissions_for(guild.me).value)
        """

        await ctx.send(f"Löydetty {len(channel_to_report)} kanavaa\nIgnorattu {len(channel_ignored)} kanavaa")



    @rep.group(name="a", aliases=["2"], hidden=True)
    #@checks.is_staff()
    async def report_all_channels(self, ctx):
        """Get all messages from channels
        Use local times, timezone is considered inside"""
        #await ctx.send(f"Viikkoraportti 2/3\nHaetaan kaikki viestit kanavalistan mukaan")
        #await ctx.send(f"Kanavien, joilla on paljon viestejä, hakeminen saattaa kestää minuutteja. Ole kärsivällinen (kanavien nimien näyttäminen piilotettu)")

        if self.mode == "top20":
            get_reactors = False

            end = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            start = end - datetime.timedelta(days=60)
        else:
            get_reactors = False
            get_reactors = True #Fetching all users who have reacted is really slow. Disable it for faster

            #start = datetime.datetime(2019, 11, 24, 9, 0, 0)
            #end = datetime.datetime(2019, 12, 29, 0, 0, 0)
            #end = datetime.datetime(2020, 1, 1, 0, 0, 0)
            #start = datetime.datetime(2018, 5, 1, 0, 0, 0)
            end = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            start = end - datetime.timedelta(days=7)

        #await ctx.send(f"Haetaan viestit aikaväliltä: {start} - {end}")
        message_header = f"Viikkoraportin generointi, viestit aikaväliltä: {start} - {end}\n"
        self.message_handle = await ctx.send(message_header)

        # Timezone difference for messages in UTC
        timezone_dt = datetime.datetime.now(datetime.timezone(datetime.timedelta(0))).astimezone().tzinfo.utcoffset(None)

        all_messages = []
        all_roles = {}

        test = 5

        total = 0
        total_reactions = 0

        guild = discord.utils.get(self.bot.guilds, id=config.guild_id)

        for category in guild.categories:
            if category.id in config.ignored_category:
                #await ctx.send(f"Ignorattu kategoria: {category.name}")
                pass
                # not run for ignored categories
            else:
                await self.message_handle.edit(content=f"{message_header}Haetaan viestejä kategoriasta: {category.name}")
                for channel in category.channels:
                    if str(channel.type) == "text" and channel.permissions_for(guild.me).value > 0:
                        if not channel.id in config.ignored_channels:
                            count = 0
                            reactions_count = 0
                            try:
                                async for message in channel.history(limit=None, after=start-timezone_dt, before=end-timezone_dt):
                                    count += 1
                                    #print (message)
                                    #print (message.id, str(message.type), message.created_at, message.channel.category_id, message.channel.category, message.channel.id, message.channel.name, message.author.id, message.author.discriminator, message.author.name, message.author.display_name, message.author.nick, message.author.bot, message.reactions)
                                    roles = []
                                    if hasattr(message.author, 'roles'):
                                        for r in message.author.roles:
                                            roles.append(r.id)
                                            if not r.id in all_roles.keys():
                                                all_roles[r.id] = r.name
                                    reactions = []
                                    for r in message.reactions:
                                        reaction = {}
                                        if isinstance(r.emoji, str):
                                            reaction['name'] = r.emoji
                                            reaction['id'] = None
                                        else:
                                            reaction['name'] = r.emoji.name
                                            reaction['id'] = r.emoji.id
                                        reaction['count'] = r.count
                                        users = []
                                        if get_reactors:
                                            async for u in r.users():
                                                users.append(int(u.id))
                                                reactions_count += 1
                                        reaction['users'] = users
                                        reactions.append(reaction)
                                    all_messages.append({'m_id': int(message.id),
                                                        'm_type': str(message.type),
                                                        'm_created_at': str(message.created_at+timezone_dt),
                                                        'm_reac': reactions,
                                                        'cha_cat_id': int(message.channel.category_id),
                                                        'cha_cat': str(message.channel.category),
                                                        'cha_id': int(message.channel.id),
                                                        'cha_name': str(message.channel.name),
                                                        'aut_id': int(message.author.id),
                                                        'aut_dis': int(message.author.discriminator),
                                                        'aut_name': str(message.author.name),
                                                        'aut_disp': str(message.author.display_name),
                                                        'aut_nick': str(message.author.nick) if hasattr(message.author, 'nick') else str(None),
                                                        'aut_roles': roles,
                                                        'aut_bot': bool(message.author.bot)})
                                total += count
                                total_reactions += reactions_count
                            except:
                                print("ERROR on get channel messages: Ignored", category.name, channel.name)
                                await ctx.send(f"Jokin virhe tapahtunut viestien haussa kanavalta ({category.name}) {channel.name}, Ignorattu")
                                #raise
                        else:
                            #channel_ignored.append(channel)
                            #cat_ignored += 1
                            pass
                    else:
                        #channel_no_premission_or_voice.append(channel)
                        pass

                    test -=1
                    if not test and testrun: # break from channels
                        break
        """

        channels = pickle.load( open( CHANNELS_FILE, "rb" ) )
        #print(len(channels))

        for c in channels:
            count = 0
            reactions_count = 0
            channel = discord.utils.get(guild.channels, id=c[0])
            try:
                async for message in channel.history(limit=None, after=start, before=end):
                    count += 1
                    #print (message)
                    #print (message.id, str(message.type), message.created_at, message.channel.category_id, message.channel.category, message.channel.id, message.channel.name, message.author.id, message.author.discriminator, message.author.name, message.author.display_name, message.author.nick, message.author.bot, message.reactions)
                    roles = []
                    if hasattr(message.author, 'roles'):
                        for r in message.author.roles:
                            roles.append(r.id)
                            if not r.id in all_roles.keys():
                                all_roles[r.id] = r.name
                    reactions = []
                    for r in message.reactions:
                        reaction = {}
                        if isinstance(r.emoji, str):
                            reaction['name'] = r.emoji
                            reaction['id'] = None
                        else:
                            reaction['name'] = r.emoji.name
                            reaction['id'] = r.emoji.id
                        reaction['count'] = r.count
                        users = []
                        if get_reactors:
                            async for u in r.users():
                                users.append(int(u.id))
                                reactions_count += 1
                        reaction['users'] = users
                        reactions.append(reaction)
                    all_messages.append({'m_id': int(message.id),
                                        'm_type': str(message.type),
                                        'm_created_at': str(message.created_at),
                                        'm_reac': reactions,
                                        'cha_cat_id': int(message.channel.category_id),
                                        'cha_cat': str(message.channel.category),
                                        'cha_id': int(message.channel.id),
                                        'cha_name': str(message.channel.name),
                                        'aut_id': int(message.author.id),
                                        'aut_dis': int(message.author.discriminator),
                                        'aut_name': str(message.author.name),
                                        'aut_disp': str(message.author.display_name),
                                        'aut_nick': str(message.author.nick) if hasattr(message.author, 'nick') else str(None),
                                        'aut_roles': roles,
                                        'aut_bot': bool(message.author.bot)})
                #print(c[3], c[1], "messages:", count, reactions_count)
                #await ctx.send(f"{c[3]} {c[1]} viestejä: {count}, reaktioita: {reactions_count}")
                total += count
                total_reactions += reactions_count
            except:
                print("ERROR on get channel messages: Ignored", c[3], c[1])
                await ctx.send(f"Jokin virhe tapahtunut viestien haussa kanavalta {c[1]}, Ignorattu")
                #raise
            test -=1
            if not test and testrun:
                break

        """

        #pprint(all_roles)

        all_members = {}
        for member in guild.members:
            try:
                all_members[int(member.id)] = {
                    'aut_dis': int(member.discriminator),
                    'aut_name': str(member.name),
                    'aut_disp': str(member.display_name),
                    'aut_nick': str(member.nick) if hasattr(member, 'nick') else str(None),
                    'aut_roles': [r.id for r in member.roles],
                    'aut_bot': bool(member.bot)
                    }

            except:
                print("ERROR on get members: Ignored", member)
                await ctx.send(f"Jokin virhe tapahtunut käyttäjien haussa, ignorattu")
                #raise


        #print(len(all_messages), total, total_reactions)
        #await ctx.send(f"Löydetty yhteensä {len(all_messages)} viestiä ja {total_reactions} reaktiota")
        await self.message_handle.edit(content=f"{message_header}Löydetty yhteensä {len(all_messages)} viestiä, {total_reactions} reaktiota ja {len(all_members)} käyttäjää")
        pickle.dump( (all_messages, all_roles, all_members), open( MESSAGES_FILE, "wb" ) )



    @rep.group(name="r", aliases=["3"], hidden=True)
    #@checks.is_staff()
    async def create_report(self, ctx):
        """Create report from messages"""
        #await ctx.send(f"Viikkoraportti 3/3\nLuetaan tiedot haetuista viesteistä")

        """
        Laske ilmentymät viesteistä
        """

        messages, all_roles, all_members = pickle.load( open( MESSAGES_FILE, "rb" ) )
        #print(len(messages))
        #pprint(all_roles)
        #pprint(all_members)

        aamuvirkut = [5,6,7,8]
        total_morning = 0

        total_staff_messages = 0
        total_vaikuttaja_messages = 0
        total_paimen_messages = 0
        total_aihe_messages = 0
        total_other_messages = 0
        total_none_messages = 0

        days = {}
        hours = {}

        authors = {}
        channels = {}
        categories = {}
        reactions = {}
        roles = {}

        juttu_messages = []

        first = None
        last = None


        count = 50
        for m in messages:
            try:
                m['m_created_at'] = datetime.datetime.strptime(m['m_created_at'], '%Y-%m-%d %H:%M:%S.%f')
            except:
                m['m_created_at'] = datetime.datetime.strptime(m['m_created_at'], '%Y-%m-%d %H:%M:%S')
            #print(m)

            if not first or first > m['m_created_at']:
                first = m['m_created_at']
            if not last or last < m['m_created_at']:
                last = m['m_created_at']

            if m['aut_id'] not in authors:
                try:
                    authors[m['aut_id']] = {'name': m['aut_nick'].replace(',', '') if m['aut_nick'] != 'None' else m['aut_disp'].replace(',', '') if m['aut_disp'] != 'None' else m['aut_name'].replace(',', ''), 'messages': 1, 'channels': {}, 'morning': 0, 'morning_channels': {}}
                except:
                    print("ERROR on author name!!!", m['aut_nick'], m['aut_disp'], m['aut_name'])
                    authors[m['aut_id']] = {'name': m['aut_name'].replace(',', ''), 'messages': 1, 'channels': {}, 'morning': 0, 'morning_channels': {}}
                finally:
                    if m['cha_id'] not in authors[m['aut_id']]['channels']:
                        authors[m['aut_id']]['channels'][m['cha_id']] = 1
                    else:
                        authors[m['aut_id']]['channels'][m['cha_id']] += 1

                    for r in m['aut_roles']:
                        if r not in roles:
                            roles[r] = [m['aut_id']]
                        else:
                            roles[r].append(m['aut_id'])

            else:
                authors[m['aut_id']]['messages'] += 1
                if m['cha_id'] not in authors[m['aut_id']]['channels']:
                    authors[m['aut_id']]['channels'][m['cha_id']] = 1
                else:
                    authors[m['aut_id']]['channels'][m['cha_id']] += 1

            if m['m_created_at'].hour in aamuvirkut:
                authors[m['aut_id']]['morning'] += 1
                total_morning += 1
                if m['cha_id'] not in authors[m['aut_id']]['morning_channels']:
                    authors[m['aut_id']]['morning_channels'][m['cha_id']] = 1
                else:
                    authors[m['aut_id']]['morning_channels'][m['cha_id']] += 1

            if m['cha_id'] not in channels:
                channels[m['cha_id']] = {'name': m['cha_name'], 'messages': 1, 'cha_cat': m['cha_cat'], 'authors': {m['aut_id']: 1}}
            else:
                channels[m['cha_id']]['messages'] += 1
                if m['aut_id'] not in channels[m['cha_id']]['authors']:
                    channels[m['cha_id']]['authors'][m['aut_id']] = 1
                else:
                    channels[m['cha_id']]['authors'][m['aut_id']] += 1

            if m['cha_cat_id'] not in categories:
                categories[m['cha_cat_id']] = {'name': m['cha_cat'], 'messages': 1, 'authors': {m['aut_id']: 1}}
            else:
                categories[m['cha_cat_id']]['messages'] += 1
                if m['aut_id'] not in categories[m['cha_cat_id']]['authors']:
                    categories[m['cha_cat_id']]['authors'][m['aut_id']] = 1
                else:
                    categories[m['cha_cat_id']]['authors'][m['aut_id']] += 1

            #select between m['m_created_at'].weekday() or m['m_created_at'].day, depending on your need
            if m['m_created_at'].weekday() not in days.keys():
                days[m['m_created_at'].weekday()] = {'messages': 1, 'day': m['m_created_at'], 'w_day': VIIKONPAIVA[m['m_created_at'].strftime("%A")], 'authors': {m['aut_id']: 1}}
            else:
                days[m['m_created_at'].weekday()]['messages'] += 1
                if m['aut_id'] not in days[m['m_created_at'].weekday()]['authors']:
                    days[m['m_created_at'].weekday()]['authors'][m['aut_id']] = 1
                else:
                    days[m['m_created_at'].weekday()]['authors'][m['aut_id']] += 1

            if m['m_created_at'].hour not in hours.keys():
                hours[m['m_created_at'].hour] = {'messages': 1, 'authors': {m['aut_id']: 1}}
            else:
                hours[m['m_created_at'].hour]['messages'] += 1
                if m['aut_id'] not in hours[m['m_created_at'].hour]['authors']:
                    hours[m['m_created_at'].hour]['authors'][m['aut_id']] = 1
                else:
                    hours[m['m_created_at'].hour]['authors'][m['aut_id']] += 1


            for r in m['m_reac']:
                if r['name'] not in reactions:
                    reactions[r['name']] = {'count': r['count'], 'authors': {m['aut_id']: 1}, 'channels': {m['cha_id']: 1}, 'users': {}}
                else:
                    reactions[r['name']]['count'] += r['count']
                    if m['aut_id'] not in reactions[r['name']]['authors']:
                        reactions[r['name']]['authors'][m['aut_id']] = 1
                    else:
                        reactions[r['name']]['authors'][m['aut_id']] += 1
                    if m['cha_id'] not in reactions[r['name']]['channels']:
                        reactions[r['name']]['channels'][m['cha_id']] = 1
                    else:
                        reactions[r['name']]['channels'][m['cha_id']] += 1

                for u in r['users']:
                    if u not in reactions[r['name']]['users']:
                        reactions[r['name']]['users'][u] = 1
                    else:
                        reactions[r['name']]['users'][u] += 1

                if r['name'] == 'juttu':
                    #pprint(m)
                    juttu_messages.append(m)


            if set(config.role_staff.keys()).intersection(m['aut_roles']):
                total_staff_messages += 1
            elif set(config.role_vaikuttaja.keys()).intersection(m['aut_roles']):
                total_vaikuttaja_messages += 1
            elif set(config.role_paimen.keys()).intersection(m['aut_roles']):
                total_paimen_messages += 1
            elif set(config.role_aihe.keys()).intersection(m['aut_roles']):
                total_aihe_messages += 1
            elif set(config.role_other.keys()).intersection(m['aut_roles']):
                total_other_messages += 1
            else:
                total_none_messages += 1

            #if hasattr(m, 'reactions') and len(m['reactions']):
            #print(m)
            #print(m['reactions'])

            count -= 1
            if not count and testrun:
                break


        """
        Muotoile tekstitaulukko laskuista
        """

        #print('\n\n')
        #print(first.strftime("%Y-%m-%d %A %H:%M:%S"))
        #print(last.strftime("%Y-%m-%d %A %H:%M:%S"))

        quick_stats_messages = "Viestimäärä\n" + str(len(messages))
        quick_stats_users = "Aktiiviset käyttäjät\n"
        quick_stats_chat = "Topchatterit\n"
        quick_stats_morning = "Aamuvirkut\n"
        quick_stats_topic = "Aktiivisin aihekanava\n"
        quick_stats_locat = "Aktiivisin paikkakunta\n"
        quick_stats_day = "Aktiivisin päivä\n"
        quick_stats_badges = "Puheenaihe badget\n"

        otsikko_text = "Mess.is discord raprtti\nAjalta {} - {}\nYhteensä {} viestiä\n".format(first.strftime("%Y-%m-%d %A %H:%M:%S"), last.strftime("%Y-%m-%d %A %H:%M:%S"), len(messages))
        otsikko_text += "Yhteensä {} käyttäjää palvelimella joista {} on kirjoittanut viestejä aikajaksolla\n".format(len(all_members), len(authors))

        paivat_text = "Päivien viestimäärät ja kirjoittajat\nPäivä, Viestit, Prosenttia kaikista, Käyttäjä(viestit), [...]\n"
        temp = []
        for k, v in days.items():
            a_temp = []
            for ak, av in v['authors'].items():
                a_temp.append([ak, av])
            a_temp.sort(key=lambda elem: elem[1], reverse=True)
            a_temp_text = ""
            for j in a_temp:
                a_temp_text += "{} ({}), ".format(authors[j[0]]['name'], j[1])
            temp.append([v['day'].strftime("%Y-%m-%d"), v['w_day'], v['messages'], a_temp_text])
        temp.sort(key=lambda elem: elem[0])
        for l in temp:
            paivat_text += "{} {}, {}, {}%, {}\n".format(l[0], l[1], l[2], l[2]/len(messages)*100, l[3])
        temp.sort(key=lambda elem: elem[2], reverse=True)
        quick_stats_day += str(temp[0][1])

        tunnit_text = "Tuntikohtaiset veistimäärät ja kirjoittajat\nTunti, Viestit, Prosenttia kaikista, Käyttäjä(viestit), [...]\n"
        temp = []
        for k, v in hours.items():
            a_temp = []
            for ak, av in v['authors'].items():
                a_temp.append([ak, av])
            a_temp.sort(key=lambda elem: elem[1], reverse=True)
            a_temp_text = ""
            for j in a_temp:
                a_temp_text += "{} ({}), ".format(authors[j[0]]['name'], j[1])
            temp.append([k, v['messages'], a_temp_text])
        temp.sort(key=lambda elem: elem[0])
        for l in temp:
            tunnit_text += "{}, {}, {}%, {}\n".format(l[0], l[1], l[1]/len(messages)*100, l[2])


        henkilo_text = "Käyttäjien viestimäärät, yhteensä käyttäjiä:, {}\nKäyttäjä, Viestit, Prosenttia kaikista, Aamu viestit, Kanava(viestit), [...]\n".format(len(authors))
        temp = []
        for k, v in authors.items():

            a_temp = []
            for ak, av in v['channels'].items():
                a_temp.append([ak, av])
            a_temp.sort(key=lambda elem: elem[1], reverse=True)
            a_temp_text = ""
            for j in a_temp:
                a_temp_text += "{} ({}), ".format(channels[j[0]]['name'], j[1])

            m_temp = []
            for mk, mv in v['morning_channels'].items():
                m_temp.append([mk, mv])
            m_temp.sort(key=lambda elem: elem[1], reverse=True)
            m_temp_text = ""
            for j in m_temp:
                m_temp_text += "{} ({}), ".format(channels[j[0]]['name'], j[1])

            temp.append([v['name'], v['messages'], v['morning'], a_temp_text, m_temp_text])
        temp.sort(key=lambda elem: elem[1], reverse=True)
        for l in temp:
            henkilo_text += "{}, {}, {}%, {}, {}\n".format(l[0], l[1], l[1]/len(messages)*100, l[2], l[3])
        #quick_stats_chat += ", ".join([l[0] for l in temp[:5]])
        for i,n in enumerate(temp[:5]):
            quick_stats_chat += str(i+1) + ". " + str(n[0]) + " "
        quick_stats_users += str(len(authors))

        aamuvirkku_text = "Aamuvirkkujen viestimäärät ({}-{}), yhteensä, {}\nKäyttäjä, Aamuvirkkuus, Prosenttia aamuviesteistä, Kaikki viestit, Prosenttia käyttäjän viesteistä, Kanava(viestit), [...]\n".format(aamuvirkut[0], aamuvirkut[-1]+1, total_morning)
        temp.sort(key=lambda elem: elem[2], reverse=True)
        for l in temp:
            if l[2] == 0:
                break
            aamuvirkku_text += "{}, {}, {}%, {}, {}%, {}\n".format(l[0], l[2], l[2]/total_morning*100, l[1], l[2]/l[1]*100, l[4])
        #quick_stats_morning += ", ".join([l[0] for l in temp[:3]])
        for i,n in enumerate(temp[:3]):
            quick_stats_morning += str(i+1) + ". " + str(n[0]) + " "

        kanavat_text = "Kanavakohtaiset viestimäärät ja kirjoittajat, yhteensä kanavia, {}\nKanava, Aihealue, Viestit, Prosenttia kaikista, Käyttäjä(viestit), [...]\n".format(len(channels))
        temp = []
        for k, v in channels.items():
            a_temp = []
            for ak, av in v['authors'].items():
                a_temp.append([ak, av])
            a_temp.sort(key=lambda elem: elem[1], reverse=True)
            a_temp_text = ""
            for j in a_temp:
                a_temp_text += "{} ({}), ".format(authors[j[0]]['name'], j[1])
            temp.append([v['name'], v['cha_cat'], v['messages'], a_temp_text])
        temp.sort(key=lambda elem: elem[2], reverse=True)
        for l in temp:
            kanavat_text += "{}, {}, {}, {}%, {}\n".format(l[0], l[1], l[2], l[2]/len(messages)*100, l[3])
        topic_notfound = True
        locat_notfound = True
        for l in temp:
            if l[0] != "yleinen":
                if not "Paikkakunnat" in l[1] and topic_notfound:
                    # Paras aihekanava
                    topic_notfound = False
                    quick_stats_topic += str(l[0])
                if "Paikkakunnat" in l[1] and locat_notfound:
                    # Paras kaupunkikanava
                    locat_notfound = False
                    quick_stats_locat += str(l[0])

        aihealueet_text = "Aihealuekohtaiset viestimäärät ja kirjoittajat\nAihealue, Viestit, Prosenttia kaikista, Käyttäjä(viestit), [...]\n"
        temp = []
        for k, v in categories.items():
            a_temp = []
            for ak, av in v['authors'].items():
                a_temp.append([ak, av])
            a_temp.sort(key=lambda elem: elem[1], reverse=True)
            a_temp_text = ""
            for j in a_temp:
                a_temp_text += "{} ({}), ".format(authors[j[0]]['name'], j[1])
            temp.append([v['name'], v['messages'], a_temp_text])
        temp.sort(key=lambda elem: elem[1], reverse=True)
        for l in temp:
            aihealueet_text += "{}, {}, {}%, {}\n".format(l[0], l[1], l[1]/len(messages)*100, l[2])


        reactions_receiver_text = "Reaktioita viesteihin vastaanottaneet käyttäjät\nReaktio, Viestit, Käyttäjä(viestit), [...]\n"
        reactions_channels_text = "Reaktioita viesteihin vastaanottaneet kanavat\nReaktio, Viestit, Kanava(viestit), [...]\n"
        reactions_sender_text = "Reaktioita viesteihin lähettäneet käyttäjät\nReaktio, Viestit, Käyttäjä(viestit), [...]\n"
        temp = []
        for k, v in reactions.items():

            a_temp = []
            for ak, av in v['authors'].items():
                a_temp.append([ak, av])
            a_temp.sort(key=lambda elem: elem[1], reverse=True)
            a_temp_text = ""
            for j in a_temp:
                a_temp_text += "{} ({}), ".format(authors[j[0]]['name'], j[1])

            m_temp = []
            for mk, mv in v['channels'].items():
                m_temp.append([mk, mv])
            m_temp.sort(key=lambda elem: elem[1], reverse=True)
            m_temp_text = ""
            for j in m_temp:
                m_temp_text += "{} ({}), ".format(channels[j[0]]['name'], j[1])

            u_temp = []
            for uk, uv in v['users'].items():
                u_temp.append([uk, uv])
            u_temp.sort(key=lambda elem: elem[1], reverse=True)
            u_temp_text = ""
            for j in u_temp:
                try:
                    u_temp_text += "{} ({}), ".format(authors[j[0]]['name'], j[1])
                except:
                    u_temp_text += "{} ({}), ".format("tuntematon käyttäjä, ID:{}".format(j[0]), j[1])


            temp.append([k, v['count'], a_temp_text, m_temp_text, u_temp_text])
        temp.sort(key=lambda elem: elem[1], reverse=True)
        for l in temp:
            reactions_receiver_text += "{}, {}, {}\n".format(l[0], l[1], l[2])
            reactions_channels_text += "{}, {}, {}\n".format(l[0], l[1], l[3])
            reactions_sender_text += "{}, {}, {}\n".format(l[0], l[1], l[4])


        #pprint(juttu_messages)
        juttu_reactions_text = "Juttu -badgella reagoidut viestit.\nHuom. Listassa vain raportin ajalta kirjoitetut viestit. Jos aiemmalle viestille on reagoitu badgella se ei näy tässä.\nViesti ID, Viesti aika, Kanava, Kirjoittaja, Reagointu Juttu -badgella, [...]\n"
        for m in juttu_messages:
            temp = ', '.join([str(m['m_id']), str(m['m_created_at']), m['cha_name'], authors[m['aut_id']]['name']])
            for r in m['m_reac']:
                if r['name'] == 'juttu':
                    u_temp = ', '.join([authors[u]['name'] for u in r['users']])
            juttu_reactions_text += temp + ", " + u_temp + "\n"
            quick_stats_badges += authors[m['aut_id']]['name']
            quick_stats_badges += ", "
        #print(juttu_reactions_text)
        quick_stats_badges = quick_stats_badges[:-2]


        role_text = "Viestimäärät suurimman roolin mukaan\n"
        role_text += "Staff viestejä:, {}, {}%\n".format(total_staff_messages, total_staff_messages/len(messages)*100)
        role_text += "Vaikuttaja viestejä:, {}, {}%\n".format(total_vaikuttaja_messages, total_vaikuttaja_messages/len(messages)*100)
        role_text += "Paimen viestejä:, {}, {}%\n".format(total_paimen_messages, total_paimen_messages/len(messages)*100)
        role_text += "Aihealueet viestejä:, {}, {}%\n".format(total_aihe_messages, total_aihe_messages/len(messages)*100)
        role_text += "Ihminen viestejä:, {}, {}%\n".format(total_other_messages, total_other_messages/len(messages)*100)
        role_text += "Ei roolia viestejä:, {}, {}%\n".format(total_none_messages, total_none_messages/len(messages)*100)


        roles_users_text = "Käyttäjät joilla rooli\nRooli, Käyttäjiä, Prosenttia käyttäjistä, käyttäjät, [..]\n"
        temp = []
        for k, v in roles.items():
            temp.append([k, len(v), v])
        temp.sort(key=lambda elem: elem[1], reverse=True)
        for l in temp:
            roles_users_text += "{}, {}, {}%, {}\n".format(all_roles[l[0]], l[1], l[1]/len(authors)*100, ', '.join([authors[n]['name'] for n in l[2]]))


        if self.mode == "top20":
            # Feature: Top 20 users, who are not 'staff or vaikuttaja'
            henkilo_text = "Top 20 Käyttäjät\nKäyttäjä, Viestit, Prosenttia kaikista, Aamu viestit\n"
            temp = []
            for k, v in authors.items():
                temp.append([v['name'], v['messages'], v['morning'], k])
            temp.sort(key=lambda elem: elem[1], reverse=True)
            count = 1
            for l in temp:
                if l[3] not in roles[448889696907689995]: # user is not in role "vaikuttaja"
                    henkilo_text += "#{}: {}, {}, {}%, {}\n".format(count, l[0], l[1], l[1]/len(messages)*100, l[2])#, "vaik" if l[3] in roles[448889696907689995] else "None")
                    count += 1
                    if count > 20:
                        break
            await ctx.send(henkilo_text)
        else:
            # Default: week report
            file_name = "{}_{}_{}.txt".format(REPORT_FILE, first.strftime("%Y-%m-%d_%A"), last.strftime("%Y-%m-%d_%A"))

            #print(file_name)

            with open(file_name, 'w') as f:
                f.write(otsikko_text + "\n\n")
                f.write(paivat_text + "\n\n")
                f.write(tunnit_text + "\n\n")
                f.write(henkilo_text + "\n\n")
                f.write(aamuvirkku_text + "\n\n")
                f.write(kanavat_text + "\n\n")
                f.write(aihealueet_text + "\n\n")
                f.write(reactions_receiver_text + "\n\n")
                f.write(reactions_channels_text + "\n\n")
                f.write(reactions_sender_text + "\n\n")
                f.write(juttu_reactions_text + "\n\n")
                f.write(role_text + "\n\n")
                f.write(roles_users_text + "\n\n")

            with open(HEADERS_FILE, "a") as f:
                f.write("{}\n".format(file_name))

            await ctx.send("Viikkostatseihin ja kuvan generointiin tiedot\n?pi\nstats\n" +
                quick_stats_messages + "\n" +
                quick_stats_chat + "\n" +
                quick_stats_morning + "\n" +
                quick_stats_topic + "\n" +
                quick_stats_locat + "\n" +
                quick_stats_day + "\n" +
                quick_stats_badges + "\n" +
                "### tarkista PA-badget muusta listasta! ###"
            )

        #await ctx.send(f"Viikkoraportti valmis\n{file_name}")
        #await ctx.send(f"Tiedot luettu")



    @rep.group(name="g", aliases=["4"], hidden=True)
    #@checks.is_staff()
    async def upload_report_g_sheets(self, ctx):
        """Upload message data from txt to google sheets"""
        #await ctx.send(f"Viikkoraportti 4/4\nLähetetään tiedot google sheetsiin")

        with open(HEADERS_FILE, 'r') as f:
            lines = f.read().splitlines()
            file_name = lines[-1].strip()
            print (file_name)

        with open(file_name) as f:
            content = f.readlines()
        content = [x.strip().split(',') for x in content]

        sheet_title = "Viikkoraportti " + content[1][0]

        #print(len(content))
        #pprint(content)

        if testrun:
            await ctx.send(f"Testiajo, tietoja ei lähetetä")
        else:
            scope = ["https://spreadsheets.google.com/feeds",'https://www.googleapis.com/auth/spreadsheets',"https://www.googleapis.com/auth/drive.file","https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_name("creds.json", scope)
            # Authorise to Google Sheets API
            client = gspread.authorize(creds)

            #sh = client.open_by_key("1OOjP6-o6l-N-esFWTOYQ4N84MJ3r_fEkTHbHfETatlU")  # Open the test spreadhseet
            #https://stackoverflow.com/questions/34400635/how-to-write-a-table-list-of-lists-to-google-spreadsheet-using-gspread
            #my_list = [['a', 'b'], ['c', 'd'], ['e', 'f'], ['g', 'h'], ['5%', '=1+2']]

            cells_to_update = []
            for y_idx, row in enumerate(content):
                for x_idx, value in enumerate(row):
                    cells_to_update.append(gspread.models.Cell(y_idx +1, x_idx +1, value))


            sh = client.create(sheet_title)
            if hasattr(config, 'sheet_owner_email') and config.sheet_owner_email:
                sh.share(config.sheet_owner_email, perm_type='user', role='writer', notify=False)

            res = sh.sheet1.update_cells(cells_to_update, value_input_option='USER_ENTERED')
            pprint(res)

            service = build('drive', 'v3', credentials=creds)
            # Call the Drive v3 API
            results = service.files().list(pageSize=10, fields="nextPageToken, files(id, name)").execute()
            items = results.get('files', [])

            """
            if not items:
                print('No files found.')
            else:
                print('Files:')
                for item in items:
                    print(u'{0} ({1})'.format(item['name'], item['id']))
            """

            file_id = sh.id
            folder_id = config.sheets_folder_id
            # Retrieve the existing parents to remove
            file = service.files().get(fileId=file_id,
                                             fields='parents').execute()
            previous_parents = ",".join(file.get('parents'))
            # Move the file to the new folder
            file = service.files().update(fileId=file_id,
                                                addParents=folder_id,
                                                removeParents=previous_parents,
                                                fields='id, parents').execute()

            #pprint(previous_parents)
            #pprint(file)

            await ctx.send(f"Viikkoraportti valmis. Tiedot kokonaisuudessaan:\n<https://docs.google.com/spreadsheets/d/{sh.id}>")


def setup(bot):
    bot.add_cog(Report(bot))
