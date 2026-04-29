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

        embed = discord.Embed(
            title="🌸 原神 ゲームステータス",
            color=0x4A90D9,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )

        # 天然樹脂
        resin_full = notes.current_resin >= notes.max_resin
        resin_val = (
            "⚠️ **満タン！**"
            if resin_full
            else f"回復まで: {fmt_td(notes.remaining_resin_recovery_time)}"
        )
        embed.add_field(
            name="🌙 天然樹脂",
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
            name="💰 洞天宝銭",
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
            name="📋 デイリー任務",
            value=commission_val,
            inline=True,
        )

        # 参量物質変化器
        if notes.transformer is None:
            transformer_val = "未取得"
        elif notes.transformer.reached:
            transformer_val = "✅ **使用可能！**"
        else:
            transformer_val = f"残り: {fmt_td(notes.transformer_recovery_time)}"
        embed.add_field(
            name="⚗️ 参量物質変化器",
            value=transformer_val,
            inline=True,
        )

        embed.add_field(name="​", value="​", inline=False)

        # 探索派遣
        if notes.expeditions:
            lines = []
            for exp in notes.expeditions:
                try:
                    char = exp.character.name
                except AttributeError:
                    char = str(exp.character)
                if exp.status == "Finished":
                    lines.append(f"✅ {char}")
                else:
                    lines.append(f"⏳ {char}（{fmt_td(exp.remaining_time)}）")
            embed.add_field(
                name="🗺️ 探索派遣",
                value="\n".join(lines),
                inline=False,
            )
        else:
            embed.add_field(name="🗺️ 探索派遣", value="派遣なし", inline=False)

        embed.set_footer(text="最終更新")
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(GenshinCommands(bot))
