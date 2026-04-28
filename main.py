import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import discord
from discord.ext import commands
import genshin
import logging

# Server
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running!")

def run_health_check_server():
    server = HTTPServer(('0.0.0.0', 8000), HealthCheckHandler)
    server.serve_forever()

# Activate health check server
threading.Thread(target=run_health_check_server, daemon=True).start()

# Configurations
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
LTUID = os.getenv("HOYOLAB_LTUID")
LTOKEN = os.getenv("HOYOLAB_LTOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Check
@bot.event
async def on_ready():
    logging.info(f"Logged in as {bot.user}")

# Jushi Command
@bot.command()
async def jushi(ctx):
    cookies = {"ltuid_v2": LTUID, "ltoken_v2": LTOKEN}
    client = genshin.Client(cookies)
    
    try:
        # UID
        notes = await client.get_genshin_notes(856548893)
        await ctx.send(f"現在の天然樹脂: **{notes.current_resin}/{notes.max_resin}**")
    except Exception as e:
        await ctx.send(f"エラーが発生しました: {e}")

# Activate Bot
if TOKEN:
    bot.run(TOKEN)
else:
    logging.info("TOKENが設定されていません。")