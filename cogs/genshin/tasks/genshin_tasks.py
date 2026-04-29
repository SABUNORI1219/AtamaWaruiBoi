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
        self._resin_notified = False
        self._realm_notified = False
        self._transformer_notified = False
        self._expeditions_notified = False
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
            client = make_client()
            notes = await client.get_genshin_notes(GENSHIN_UID)
        except Exception as e:
            logger.error(f"[原神] ノート取得失敗: {e}")
            return

        # 天然樹脂が満タン
        if notes.current_resin >= notes.max_resin:
            if not self._resin_notified:
                await channel.send(
                    f"🌙 **[原神]** 天然樹脂が満タンになりました！"
                    f" `{notes.current_resin}/{notes.max_resin}`"
                )
                self._resin_notified = True
        else:
            self._resin_notified = False

        # 洞天宝銭が満タン
        if notes.current_realm_currency >= notes.max_realm_currency:
            if not self._realm_notified:
                await channel.send(
                    f"💰 **[原神]** 洞天宝銭が満タンになりました！"
                    f" `{notes.current_realm_currency}/{notes.max_realm_currency}`"
                )
                self._realm_notified = True
        else:
            self._realm_notified = False

        # 参量物質変化器が使用可能
        if notes.transformer and notes.transformer.reached:
            if not self._transformer_notified:
                await channel.send("⚗️ **[原神]** 参量物質変化器が使用可能になりました！")
                self._transformer_notified = True
        else:
            self._transformer_notified = False

        # 全探索派遣が完了
        if notes.expeditions:
            all_done = all(exp.status == "Finished" for exp in notes.expeditions)
            if all_done:
                if not self._expeditions_notified:
                    await channel.send("🗺️ **[原神]** 全ての探索派遣が完了しました！")
                    self._expeditions_notified = True
            else:
                self._expeditions_notified = False

    @check_status.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(GenshinTasks(bot))
