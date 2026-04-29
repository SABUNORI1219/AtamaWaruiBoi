import os
import datetime
import genshin
import discord
from discord import app_commands
from discord.ext import commands

LTUID = os.getenv("HOYOLAB_LTUID")
LTOKEN = os.getenv("HOYOLAB_LTOKEN")
GENSHIN_UID = 856548893


def make_client() -> genshin.Client:
    cookies = {"ltuid_v2": LTUID, "ltoken_v2": LTOKEN}
    client = genshin.Client(cookies)
    client.lang = "ja-jp"
    return client


def fmt_td(td: datetime.timedelta) -> str:
    """timedelta を '◯時間◯分' 形式に変換。0以下なら '完了' を返す。"""
    total = int(td.total_seconds())
    if total <= 0:
        return "完了"
    h, rem = divmod(total, 3600)
    m = rem // 60
    if h > 0:
        return f"{h}時間{m}分"
    return f"{m}分"


class GenshinCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="genshin", description="原神のゲーム内ステータスを表示します")
    async def genshin_status(self, interaction: discord.Interaction):
        await interaction.response.defer()

        if not GENSHIN_UID:
            await interaction.followup.send(
                "環境変数 `GENSHIN_UID` が設定されていません。", ephemeral=True
            )
            return

        try:
            client = make_client()
            notes = await client.get_genshin_notes(GENSHIN_UID)
        except Exception as e:
            await interaction.followup.send(f"データ取得に失敗しました: {e}", ephemeral=True)
            return

        author_name = f"UID: {GENSHIN_UID}"
        author_icon = None
        try:
            user = await client.get_genshin_user(GENSHIN_UID)
            if user and hasattr(user, "info"):
                nickname = getattr(user.info, "nickname", "Unknown")
                level = getattr(user.info, "level", "?")
                author_name = f"{nickname} (Lv.{level})"
                author_icon = getattr(user.info, "icon", getattr(user.info, "avatar_url", None))
        except Exception:
            pass # 戦績非公開などの場合はデフォルト（UIDのみ）を使用

        embed = discord.Embed(
            title="🌸 原神 ゲームステータス",
            color=0x4A90D9,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        
        if author_icon:
            embed.set_author(name=author_name, icon_url=author_icon)
        else:
            embed.set_author(name=author_name)

        icon_file = None
        if os.path.exists("assets/genshin/genshin-icon.png"):
            icon_file = discord.File("assets/genshin/genshin-icon.png", filename="genshin-icon.png")
            embed.set_thumbnail(url="attachment://genshin-icon.png")

        # 天然樹脂
        resin_full = notes.current_resin >= notes.max_resin
        resin_val = (
            "⚠️ **満タン！**"
            if resin_full
            else f"回復まで: {fmt_td(notes.remaining_resin_recovery_time)}"
        )
        embed.add_field(
            name=f"{self.bot.custom_emojis.get('genshin_jusi', '🌙')} 天然樹脂",
            value=f"`{notes.current_resin} / {notes.max_resin}`\n{resin_val}",
            inline=True,
        )

        # 洞天宝銭
        realm_full = notes.current_realm_currency >= notes.max_realm_currency
        realm_val = (
            "⚠️ **満タン！**"
            if realm_full
            else f"回復まで: {fmt_td(notes.remaining_realm_currency_recovery_time)}"
        )
        embed.add_field(
            name=f"{self.bot.custom_emojis.get('genshin_douten_housen', '💰')} 洞天宝銭",
            value=f"`{notes.current_realm_currency} / {notes.max_realm_currency}`\n{realm_val}",
            inline=True,
        )

        embed.add_field(name="​", value="​", inline=False)

        # デイリー任務
        if notes.claimed_commission_reward:
            commission_val = "✅ 達成 & 報酬受取済み"
        elif notes.completed_commissions >= notes.total_commissions:
            commission_val = "☑️ 達成済み（報酬未受取）"
        else:
            commission_val = f"⏳ {notes.completed_commissions} / {notes.total_commissions} 完了"
        embed.add_field(
            name=f"{self.bot.custom_emojis.get('genshin_daily', '📋')} デイリー任務",
            value=commission_val,
            inline=True,
        )

        # 参量物質変化器
        t_time = getattr(notes, "remaining_transformer_recovery_time", getattr(notes, "transformer_recovery_time", None))
        if t_time is None or not hasattr(t_time, "total_seconds"):
            transformer_val = "未取得または情報なし"
        elif t_time.total_seconds() <= 0:
            transformer_val = "✅ **使用可能！**"
        else:
            transformer_val = f"残り: {fmt_td(t_time)}"
        embed.add_field(
            name=f"{self.bot.custom_emojis.get('genshin_sanryou_bussitu_henkaki', '⚗️')} 参量物質変化器",
            value=transformer_val,
            inline=True,
        )

        embed.add_field(name="​", value="​", inline=False)

        # 探索派遣
        if notes.expeditions:
            lines = []
            for i, exp in enumerate(notes.expeditions, 1):
                char_obj = getattr(exp, "character", None)
                char = getattr(char_obj, "name", None) if char_obj else getattr(exp, "character_name", f"派遣{i}")
                if exp.status == "Finished":
                    lines.append(f"✅ {char}")
                else:
                    lines.append(f"⏳ {char}（{fmt_td(exp.remaining_time)}）")
            embed.add_field(
                name=f"{self.bot.custom_emojis.get('genshin_tansaku_haken', '🗺️')} 探索派遣",
                value="\n".join(lines),
                inline=False,
            )
        else:
            embed.add_field(name=f"{self.bot.custom_emojis.get('genshin_tansaku_haken', '🗺️')} 探索派遣", value="派遣なし", inline=False)

        embed.set_footer(text="最終更新")
        if icon_file:
            await interaction.followup.send(embed=embed, file=icon_file)
        else:
            await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(GenshinCommands(bot))
