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
    "cogs.wynncraft.commands.guild_cog",
    "cogs.wynncraft.commands.player_cog",
    "cogs.wynncraft.tasks.war_tracker",
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
        intents.guilds = True # ギルド情報を取得するために必要
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.custom_emojis = {} # カスタム絵文字を格納する辞書

    async def setup_hook(self):
        await self._register_custom_emojis()

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

    async def _register_custom_emojis(self):
        emoji_map = {
            "genshin_jusi": "assets/genshin/jusi.png",
            "genshin_douten_housen": "assets/genshin/douten-housen.png",
            "genshin_daily": "assets/genshin/daily.png",
            "genshin_sanryou_bussitu_henkaki": "assets/genshin/sanryou-bussitu-henkaki.png",
            "genshin_tansaku_haken": "assets/genshin/tansaku-haken.png",
            "hsr_kaitakuryoku": "assets/hsr/kaitakuryoku.png",
            "hsr_yobi_kaitakuryoku": "assets/hsr/yobi-kaitakuryoku.png",
            "hsr_irai_haken": "assets/hsr/irai-haken.png",
            "hsr_daily_kunren": "assets/hsr/daily-kunren.png",
            "hsr_mogi_utyuu": "assets/hsr/mogi-utyuu.png",
            "hsr_rekisen_yoin": "assets/hsr/rekisen-yoin.png",
        }

        try:
            app_emojis = await self.fetch_application_emojis()
        except Exception as e:
            logging.error(f"アプリケーション絵文字の取得に失敗しました: {e}")
            return

        for name, path in emoji_map.items():
            # 既に登録されているか確認
            existing_emoji = discord.utils.get(app_emojis, name=name)
            if existing_emoji:
                self.custom_emojis[name] = str(existing_emoji)
                logging.info(f"既存のアプリケーション絵文字を検出: {name} {self.custom_emojis[name]}")
                continue

            # ファイルが存在するか確認
            if not os.path.exists(path):
                logging.warning(f"絵文字ファイルが見つかりません: {path}")
                continue

            try:
                with open(path, "rb") as image:
                    emoji_bytes = image.read()
                
                # 絵文字をアップロード
                new_emoji = await self.create_application_emoji(name=name, image=emoji_bytes)
                self.custom_emojis[name] = str(new_emoji)
                logging.info(f"アプリケーション絵文字を登録しました: {name} {self.custom_emojis[name]}")
            except discord.HTTPException as e:
                logging.error(f"アプリケーション絵文字 {name} の登録に失敗しました: {e}")
            except Exception as e:
                logging.error(f"アプリケーション絵文字 {name} の登録中に予期せぬエラーが発生しました: {e}")

    async def on_ready(self):
        logging.info(f"Logged in as {self.user} (ID: {self.user.id})")


threading.Thread(target=run_health_check_server, daemon=True).start()

bot = AtamaWaruiBot()

if TOKEN:
    bot.run(TOKEN)
else:
    logging.error("DISCORD_BOT_TOKEN が設定されていません。")
