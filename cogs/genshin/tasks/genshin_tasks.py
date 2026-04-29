import os
import logging
import genshin
import discord
from discord.ext import commands, tasks

logger = logging.getLogger(__name__)

LTUID = os.getenv("HOYOLAB_LTUID")
LTOKEN = os.getenv("HOYOLAB_LTOKEN")
GENSHIN_UID = 856548893
NOTIFICATION_CHANNEL_ID = 1499041298399756438

CHECK_INTERVAL_MINUTES = 5


def make_client() -> genshin.Client:
    cookies = {"ltuid_v2": LTUID, "ltoken_v2": LTOKEN}
    client = genshin.Client(cookies)
    client.lang = "ja-jp"
    return client


class GenshinTasks(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.client = make_client()
        self.last_resin = -1
        self.last_realm_currency = -1
        self.last_transformer_reached = False
        self.completed_expeditions = set()
        self.is_first_run = True
        self.check_status.start()

    def cog_unload(self):
        self.check_status.cancel()

    @tasks.loop(minutes=CHECK_INTERVAL_MINUTES)
    async def check_status(self):
        if not GENSHIN_UID or not NOTIFICATION_CHANNEL_ID:
            return

        channel = self.bot.get_channel(NOTIFICATION_CHANNEL_ID)
        if not channel:
            return

        try:
            notes = await self.client.get_genshin_notes(GENSHIN_UID)
        except Exception as e:
            logger.error(f"[原神] ノート取得失敗: {e}")
            return

        if self.is_first_run:
            self.last_resin = notes.current_resin
            self.last_realm_currency = notes.current_realm_currency
            self.last_transformer_reached = bool(notes.transformer and notes.transformer.reached)
            if notes.expeditions:
                self.completed_expeditions = {
                    (exp.character.name if hasattr(exp.character, 'name') else str(exp.character))
                    for exp in notes.expeditions if exp.status == "Finished"
                }
            self.is_first_run = False
            return

        # 天然樹脂が満タン
        if notes.current_resin >= notes.max_resin and self.last_resin < notes.max_resin:
            await channel.send(
                f"🌙 **[原神]** 天然樹脂が満タンになりました！"
                f" `{notes.current_resin}/{notes.max_resin}`"
            )
        self.last_resin = notes.current_resin

        # 洞天宝銭が満タン
        if notes.current_realm_currency >= notes.max_realm_currency and self.last_realm_currency < notes.max_realm_currency:
            await channel.send(
                f"💰 **[原神]** 洞天宝銭が満タンになりました！"
                f" `{notes.current_realm_currency}/{notes.max_realm_currency}`"
            )
        self.last_realm_currency = notes.current_realm_currency

        # 参量物質変化器が使用可能
        current_transformer_reached = bool(notes.transformer and notes.transformer.reached)
        if current_transformer_reached and not self.last_transformer_reached:
            await channel.send("⚗️ **[原神]** 参量物質変化器が使用可能になりました！")
        self.last_transformer_reached = current_transformer_reached

        # 探索派遣が完了（差分を個別に通知）
        if notes.expeditions:
            current_completed = {
                (exp.character.name if hasattr(exp.character, 'name') else str(exp.character))
                for exp in notes.expeditions if exp.status == "Finished"
            }
            newly_completed = current_completed - self.completed_expeditions
            if newly_completed:
                names = ", ".join(newly_completed)
                await channel.send(f"🗺️ **[原神]** 探索派遣が完了しました！ ({names})")
            self.completed_expeditions = current_completed

    @check_status.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(GenshinTasks(bot))
