import os
import logging
import genshin
import discord
from discord.ext import commands, tasks

logger = logging.getLogger(__name__)

LTUID = os.getenv("HOYOLAB_LTUID")
LTOKEN = os.getenv("HOYOLAB_LTOKEN")
HSR_UID = 835717575
NOTIFICATION_CHANNEL_ID = 1499041298399756438

CHECK_INTERVAL_MINUTES = 5


def make_client() -> genshin.Client:
    cookies = {"ltuid_v2": LTUID, "ltoken_v2": LTOKEN}
    client = genshin.Client(cookies)
    client.lang = "ja-jp"
    return client


class HSRTasks(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._stamina_notified = False
        self._expeditions_notified = False
        self.check_status.start()

    def cog_unload(self):
        self.check_status.cancel()

    @tasks.loop(minutes=CHECK_INTERVAL_MINUTES)
    async def check_status(self):
        if not HSR_UID or not NOTIFICATION_CHANNEL_ID:
            return

        channel = self.bot.get_channel(NOTIFICATION_CHANNEL_ID)
        if not channel:
            return

        try:
            client = make_client()
            notes = await client.get_starrail_notes(HSR_UID)
        except Exception as e:
            logger.error(f"[HSR] ノート取得失敗: {e}")
            return

        # 開拓力が満タン
        if notes.current_stamina >= notes.max_stamina:
            if not self._stamina_notified:
                await channel.send(
                    f"{self.bot.custom_emojis.get('hsr_kaitakuryoku', '⚡')} **[スターレイル]** 開拓力が満タンになりました！"
                    f" `{notes.current_stamina}/{notes.max_stamina}`"
                )
                self._stamina_notified = True
        else:
            self._stamina_notified = False

        # 全依頼が完了
        if notes.expeditions:
            all_done = all(exp.status == "Finished" for exp in notes.expeditions)
            if all_done:
                if not self._expeditions_notified:
                    await channel.send(f"{self.bot.custom_emojis.get('hsr_irai_haken', '🗺️')} **[スターレイル]** 全ての依頼が完了しました！")
                    self._expeditions_notified = True
            else:
                self._expeditions_notified = False

    @check_status.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(HSRTasks(bot))
