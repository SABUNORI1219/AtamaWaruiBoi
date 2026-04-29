import os
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

import discord
from discord.ext import commands

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GUILD_ID = os.getenv("DISCORD_GUILD_ID")

EXTENSIONS = [
    "cogs.genshin.commands.genshin_commands",
    "cogs.genshin.tasks.genshin_tasks",
    "cogs.hsr.commands.hsr_commands",
    "cogs.hsr.tasks.hsr_tasks",
]


class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running!")

    def log_message(self, format, *args):
        pass


def run_health_check_server():
    server = HTTPServer(("0.0.0.0", 8000), HealthCheckHandler)
    server.serve_forever()


class AtamaWaruiBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)

    async def setup_hook(self):
        for ext in EXTENSIONS:
            await self.load_extension(ext)
            logging.info(f"Loaded: {ext}")

        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logging.info(f"Slash commands synced to guild {GUILD_ID}")
        else:
            await self.tree.sync()
            logging.info("Slash commands synced globally")

    async def on_ready(self):
        logging.info(f"Logged in as {self.user} (ID: {self.user.id})")


threading.Thread(target=run_health_check_server, daemon=True).start()

bot = AtamaWaruiBot()

if TOKEN:
    bot.run(TOKEN)
else:
    logging.error("DISCORD_BOT_TOKEN が設定されていません。")
