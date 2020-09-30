from discord.ext import tasks, commands
from library.common import checks
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from pprint import pprint
from PIL import Image, ImageFont, ImageDraw

import discord
import gspread
import datetime
import asyncio
import logging

import config

testrun = False
testrun = True # Enable testrun when developing

DAYS = ["ma", "ti", "ke", "to", "pe", "la", "su"]

STATS_HEAD = ["viesti", "chat", "aamu", "aihe", "paikka", "pävä", "badge"]

PATH_PREFIX = "pics/"

# TODO: multiple files: https://stackoverflow.com/a/51916616

# TODO: different color charecters: https://stackoverflow.com/questions/19206840/multicolored-text-with-pil

def fontSize(size):
	return ImageFont.truetype(PATH_PREFIX+"whitney-black/Whitney-Black.ttf", size)

def day(day, line1=None, time1=None, line2=None, time2=None, alt=False):
    day = day.strip()
    line1 = line1.strip() if line1 else None
    time1 = time1.strip() if time1 else None
    line2 = line2.strip() if line2 else None
    time2 = time2.strip() if time2 else None

    # print(day, line1, time1, line2, time2)

    width = 1400
    height = 150

    day_width = 220
    time_width = 200

    #img = Image.new('RGB', (1400,150), (255, 255, 255))
    img = Image.new('RGB', (width, height), "PURPLE")


    dark = (0,0,0,75)
    light = (255,255,255,55)

    indent_color = light

    #https://stackoverflow.com/questions/43618910/pil-drawing-a-semi-transparent-square-overlay-on-image
    overlay = Image.new('RGBA', (width, height), (0,0,0,0))
    draw = ImageDraw.Draw(overlay)
    if line2 == None: # single line day text
        if alt:
            draw.rectangle(((0,0), (day_width+1, height+1)), indent_color)
            draw.rectangle(((width-time_width,0), (width+1, height+1)), indent_color)
        else:
            draw.rectangle(((day_width,0), (width-time_width+1, height+1)), indent_color)

    else:
        if alt:
            # day
            draw.rectangle(((0,0), (day_width+1, height+1)), indent_color)
            # text middle
            draw.rectangle(((day_width,height/2-2), (width-time_width+1, height/2+2)), indent_color)
            # times with brake line
            #draw.rectangle(((width-time_width,0), (width+1, height/2-2)), indent_color)
            #draw.rectangle(((width-time_width,height/2+2), (width+1, height+1)), indent_color)
            # time without brake line
            draw.rectangle(((width-time_width,0), (width+1, height+1)), indent_color)
        else:
            draw.rectangle(((day_width,0), (width-time_width+1, height/2-2)), indent_color)
            draw.rectangle(((day_width,height/2+2), (width-time_width+1, height+1)), indent_color)

    img = img.convert("RGBA")
    img = Image.alpha_composite(img, overlay)
    img = img.convert("RGB")


    font = fontSize(120)
    drawtext = ImageDraw.Draw(img)
    w, h = drawtext.textsize(day, font=font)
    drawtext.text(((day_width-w)/2, 0), day, (0,0,0), font=font)

    if line1 and line2 == None:
        font = fontSize(60)
        #drawtext = ImageDraw.Draw(img)
        drawtext.text((day_width+15, 40), line1, (0,0,0), font=font)
        if time1:
            w, h = drawtext.textsize(time1, font=font)
            drawtext.text((width-time_width+(time_width-w)/2, 40), time1, (0,0,0), font=font)
    elif line1:
        font = fontSize(60)
        #drawtext = ImageDraw.Draw(img)
        drawtext.text((day_width+15, 0), line1, (0,0,0), font=font)
        if time1:
            w, h = drawtext.textsize(time1, font=font)
            drawtext.text((width-time_width+(time_width-w)/2, 0), time1, (0,0,0), font=font)

        drawtext.text((day_width+15, 75), line2, (0,0,0), font=font)
        if time2:
            w, h = drawtext.textsize(time2, font=font)
            drawtext.text((width-time_width+(time_width-w)/2, 75), time2, (0,0,0), font=font)

    img.save(PATH_PREFIX+day+".png", "PNG")
    return img

class Pics(commands.Cog):
    """Kuvien tuottaminen ohjelmakalenteriin"""

    global logger
    logger = logging.getLogger("bot")

    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="pics", aliases=["pi"], hidden=True, pass_context = True)
    #@checks.is_staff()
    async def rep(self, ctx, *args, **kwargs):
        """Kuvien tuottaminen ohjelmakalenteriin"""
        logger.info(f"Kuvien generointi. Komennon suorittaja: {ctx.author.display_name} "
                    f"(ID: {ctx.author.id}).")

        self.args = args
        self.kwargs = kwargs

        if ctx.invoked_subcommand is None:
            r = self.bot.get_cog("Pics")
            if len(args) > 0 and args[0].startswith("stat"):
                await r.stats.invoke(ctx)
            else:
                await r.calendar.invoke(ctx)

    @rep.group(name="p", aliases=["9"], hidden=True)
    #@checks.is_staff()
    async def calendar(self, ctx, *args, **kwargs):
        """Generate calendar pictures from argument texts"""
        await ctx.send(f"Kuvien generointi ohjelmakalenteriin")

        if not self.args:
            self.args = args
        if not self.kwargs:
            self.kwargs = kwargs

        if testrun:
            #await ctx.send(f"{args}\n{kwargs}")
            await ctx.send(f"{self.args}\n{self.kwargs}")

        title = False

        response = ["parsed from: \n?pi"]
        for a in self.args:
            a = a.strip()
            if " " in a or "\n" in a:
                response.append('"' + a + '"')
            else:
                response.append(a)

            if a.startswith("title="):
                title = a.replace("title=", "")
            else:
                text = a

        await ctx.send(" \n".join(response))

        """ Arg parse """
        all_caps = True

        day_text = []
        day_text_index = -1
        day_line_text_index = 0

        for l in text.splitlines():
            l = l.strip()
            if not l: # empty lines
                pass
            elif l.lower() in DAYS:
                #print("##DAY", l)
                day_text_index += 1
                day_text.append([l if not all_caps else l.upper()])
                day_line_text_index = 0
            elif day_text_index < 0: # no day spesified
                pass
            elif l[0].isdigit():
                if day_line_text_index:
                    #print("##TIME", l)
                    if len(l) < 3:
                        l += ":00"
                    day_text[day_text_index][day_line_text_index].append(l if not all_caps else l.upper())
                else:
                    pass
                    #print("No event for time")
            else:
                #print("##OTH", l)
                day_text[day_text_index].append([l if not all_caps else l.upper()])
                day_line_text_index += 1

        # pprint(day_text)

        """ Picture generation """
        alt = 0

        day_height = 150
        title_height = 150
        width = 1400
        height = title_height + 7*day_height

        # print(datetime.datetime.now().isocalendar()[1])

        if not title:
            title = "VKO " + str(datetime.datetime.now().isocalendar()[1]) + " Ohjelma"
        if all_caps:
            title = title.upper()

        """
        week = [
            day('MA', "SKRIBBL.IO", "19:00", alt=1 if alt else 0),
            day('TI', "LEIKITÄÄN GRAAFIKOITA", "19:00", alt=0 if alt else 1),
            day('KE', "PAINTBALL-VKL JÄLKIFIILISTELY", "19:00", alt=1 if alt else 0),
            day('TO', alt=0 if alt else 1),
            day('PE', alt=1 if alt else 0),
            day('LA', "AGAR.IO", "17:00", "KEHONHUOLTO", "19:00", alt=0 if alt else 1),
            day('SU', "AGAR.IO", "17:00", "MESSIS-UUTISET", "19:00", alt=1 if alt else 0),
            ]
        """
        week = []
        for i,n in enumerate(day_text):
            if len(n) == 1:
                week.append(day(n[0]), alt=i%2)
            elif len(n) == 2:
                week.append(day(n[0], n[1][0], n[1][1] if len(n[1])>1 else None, alt=i%2))
            else:
                week.append(day(n[0], n[1][0], n[1][1] if len(n[1])>1 else None,
                                        n[2][0], n[2][1] if len(n[2])>1 else None, alt=i%2))

        img = Image.new('RGB', (width, height), "PURPLE")
        font = fontSize(120)
        draw = ImageDraw.Draw(img)
        w, h = draw.textsize(title, font=font)
        draw.text(((width-w)/2, 0), title, (0,0,0), font=font)

        for i,n in enumerate(week):
            #print(i,n)
            img.paste(n, (0,title_height+day_height*i))

        img.save(PATH_PREFIX+"week.png", "PNG")
        if testrun:
            await ctx.send(f"Testrun, no file send")
        else:
            await ctx.send(file=discord.File(PATH_PREFIX+"week.png"))


    @rep.group(name="ps", aliases=["10"], hidden=True)
    #@checks.is_staff()
    async def stats(self, ctx, *args, **kwargs):
        """Generate calendar pictures from argument texts"""
        await ctx.send(f"Kuvien generointi ohjelmakalenteriin")

        if not self.args:
            self.args = args
        if not self.kwargs:
            self.kwargs = kwargs

        if testrun:
            #await ctx.send(f"{args}\n{kwargs}")
            await ctx.send(f"{self.args}\n{self.kwargs}")

        all_caps = True

        title = False

        response = ["parsed from: \n?pi"]
        for a in self.args:
            a = a.strip()
            if " " in a or "\n" in a:
                response.append('"' + a + '"')
            else:
                response.append(a)

            if a.startswith("title="):
                title = a.replace("title=", "")
            else:
                text = a

        await ctx.send(" \n".join(response))

        if not title:
            title = "VKO " + str(datetime.datetime.now().isocalendar()[1] + 1) + " statsit"
        if all_caps:
            title = title.upper()

        # print(title)

        """ Arg parse """
        data = []

        for l in text.splitlines():
            l = l.strip()
            if not l: # empty lines
                pass
            #elif l.lower() in STATS_HEAD:
            #    print("### HEAD", l)
            if len(l) > 25:
                # cut too long text into 2 lines
                pos = l[20:].find(" ") + 20
                l = l[:pos] + "\n" + l[pos+1:]
            data.append(l if not all_caps else l.upper())

        # pprint(data)

        """ Picture generation """
        background_image = Image.open(PATH_PREFIX+"viikko-statsit_pohja.jpg")
        img = background_image
        width, height = img.size

        #1080 / 8 = 35 # equal height rows
        row_height = 120
        row_width = 380
        title_height = height - 7*row_height

        font = fontSize(120)
        draw = ImageDraw.Draw(img)
        w, h = draw.textsize(title, font=font)
        draw.text(((width-w)/2, (title_height-h)/2-5), title, (245,245,245), font=font)

        font = fontSize(50)
        for i,n in enumerate(data):
            if "\n" in n:
                draw.text((row_width + 25, title_height + i*row_height + 5), n, (253, 173, 14), font=font)
                # double line
            else:
                draw.text((row_width + 25, title_height + i*row_height + 30), n, (253, 173, 14), font=font)

        img.save(PATH_PREFIX+"stats.png", "PNG")
        if testrun:
            await ctx.send(f"Testrun, no file send")
        else:
            await ctx.send(file=discord.File(PATH_PREFIX+"stats.png"))


def setup(bot):
    bot.add_cog(Pics(bot))
