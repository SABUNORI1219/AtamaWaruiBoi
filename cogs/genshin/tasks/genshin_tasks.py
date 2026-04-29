import os
import logging
import datetime
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
        self.last_daily_notification_date = None
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
            
            t_time = getattr(notes, "remaining_transformer_recovery_time", getattr(notes, "transformer_recovery_time", None))
            self.last_transformer_reached = (t_time is not None and hasattr(t_time, "total_seconds") and t_time.total_seconds() <= 0)
            if notes.expeditions:
                self.completed_expeditions = set()
                for i, exp in enumerate(notes.expeditions, 1):
                    if exp.status == "Finished":
                        char_obj = getattr(exp, "character", None)
                        char_name = getattr(char_obj, "name", None) if char_obj else getattr(exp, "character_name", f"派遣{i}")
                        self.completed_expeditions.add(char_name)
            self.is_first_run = False
            return

        # 天然樹脂が溢れそう (180以上)
        RESIN_THRESHOLD = 180
        if notes.current_resin >= RESIN_THRESHOLD and self.last_resin < RESIN_THRESHOLD:
            embed = discord.Embed(
                description=f"{self.bot.custom_emojis.get('genshin_jusi', '🌙')} **[原神]** 天然樹脂が溢れそうです！\n`{notes.current_resin}/{notes.max_resin}`",
                color=0x4A90D9
            )
            await channel.send(embed=embed)
        self.last_resin = notes.current_resin

        # 洞天宝銭が溢れそう (2000以上)
        REALM_THRESHOLD = 2000
        if notes.current_realm_currency >= REALM_THRESHOLD and self.last_realm_currency < REALM_THRESHOLD:
            embed = discord.Embed(
                description=f"{self.bot.custom_emojis.get('genshin_douten_housen', '💰')} **[原神]** 洞天宝銭が溢れそうです！\n`{notes.current_realm_currency}/{notes.max_realm_currency}`",
                color=0x4A90D9
            )
            await channel.send(embed=embed)
        self.last_realm_currency = notes.current_realm_currency

        # デイリー任務 (21時以降で未受取)
        now_jst = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
        if now_jst.hour >= 21 and not notes.claimed_commission_reward:
            if self.last_daily_notification_date != now_jst.date():
                embed = discord.Embed(
                    description=f"{self.bot.custom_emojis.get('genshin_daily', '⚠️')} **[原神]** 21時を過ぎていますが、デイリー任務の追加報酬が未受取です！忘れずにキャサリンへ！",
                    color=0x4A90D9
                )
                await channel.send(embed=embed)
                self.last_daily_notification_date = now_jst.date()

        # 参量物質変化器が使用可能
        t_time = getattr(notes, "remaining_transformer_recovery_time", getattr(notes, "transformer_recovery_time", None))
        current_transformer_reached = (t_time is not None and hasattr(t_time, "total_seconds") and t_time.total_seconds() <= 0)
        if current_transformer_reached and not self.last_transformer_reached:
            embed = discord.Embed(
                description=f"{self.bot.custom_emojis.get('genshin_sanryou_bussitu_henkaki', '⚗️')} **[原神]** 参量物質変化器が使用可能になりました！",
                color=0x4A90D9
            )
            await channel.send(embed=embed)
        self.last_transformer_reached = current_transformer_reached

        # 探索派遣が完了（差分を個別に通知）
        if notes.expeditions:
            current_completed = set()
            for i, exp in enumerate(notes.expeditions, 1):
                if exp.status == "Finished":
                    char_obj = getattr(exp, "character", None)
                    char_name = getattr(char_obj, "name", None) if char_obj else getattr(exp, "character_name", f"派遣{i}")
                    current_completed.add(char_name)
            
            newly_completed = current_completed - self.completed_expeditions
            if newly_completed:
                names = ", ".join(newly_completed)
                embed = discord.Embed(
                    description=f"{self.bot.custom_emojis.get('genshin_tansaku_haken', '🗺️')} **[原神]** 探索派遣が完了しました！ ({names})",
                    color=0x4A90D9
                )
                await channel.send(embed=embed)
            self.completed_expeditions = current_completed

    @check_status.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(GenshinTasks(bot))
