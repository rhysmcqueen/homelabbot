from discord.ext import commands
import discord
import subprocess
import CloudFlare
#from dotenv import load_dotenv

#load_dotenv()
#BOT_TOKEN
BOT_TOKEN = ""
CHANNEL_ID = ""

#CLOUDFLARE
CF_EMAIL= ""
CF_API_KEY = ""
CF_TOKEN = ""
DOMAIN= ""
bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())
cf = CloudFlare.CloudFlare(email=CF_EMAIL, key=CF_API_KEY)


@bot.event
async def on_ready():
        print("McQueenLab.net Bot is Online")
        channel = bot.get_channel(CHANNEL_ID)
 #       await channel.send("McQueenLab.net Bot is Online")

@bot.command()
async def ping(ctx, x):
        process = subprocess.Popen(['ping', '-c 4', x], 
                           stdout=subprocess.PIPE,
                           universal_newlines=True)
        while True:
         output = process.stdout.readline()
         await ctx.send(output.strip())
         # Do something else
         return_code = process.poll()
         if return_code is not None:
                await ctx.send('RETURN CODE', return_code)
                # Process has finished, read rest of the output 
                for output in process.stdout.readlines():
                        await ctx.send(output.strip())
                break
@bot.command()
async def cfzone(ctx):
        cf = CloudFlare.CloudFlare(email=CF_EMAIL, key=CF_API_KEY)
        zones = cf.zones.get()
        for zone in zones:
                zone_name = zone['name']
                zone_id = zone['id']
                settings_ipv6 = cf.zones.settings.ipv6.get(zone_id)
                ipv6_on = settings_ipv6['value']
                output = zone_id + ipv6_on + zone_name
        await ctx.send()
bot.run(BOT_TOKEN)