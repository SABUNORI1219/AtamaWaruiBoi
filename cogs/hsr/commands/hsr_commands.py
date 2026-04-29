import os
import datetime
import genshin
import discord
from discord import app_commands
from discord.ext import commands

LTUID = os.getenv("HOYOLAB_LTUID")
LTOKEN = os.getenv("HOYOLAB_LTOKEN")
HSR_UID = 835717575


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


class HSRCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="hsr", description="崩壊：スターレイルのゲーム内ステータスを表示します")
    async def hsr_status(self, interaction: discord.Interaction):
        await interaction.response.defer()

        if not HSR_UID:
            await interaction.followup.send(
                "環境変数 `HSR_UID` が設定されていません。", ephemeral=True
            )
            return

        try:
            client = make_client()
            notes = await client.get_starrail_notes(HSR_UID)
        except Exception as e:
            await interaction.followup.send(f"データ取得に失敗しました: {e}", ephemeral=True)
            return

        author_name = f"UID: {HSR_UID}"
        author_icon = None
        try:
            user = await client.get_starrail_user(HSR_UID)
            if user and hasattr(user, "info"):
                nickname = getattr(user.info, "nickname", "Unknown")
                level = getattr(user.info, "level", "?")
                author_name = f"{nickname} (Lv.{level})"
                author_icon = getattr(user.info, "icon", getattr(user.info, "avatar_url", None))
        except Exception:
            pass # 戦績非公開などの場合はデフォルト（UIDのみ）を使用

        embed = discord.Embed(
            title="🚂 崩壊：スターレイル ゲームステータス",
            color=0x9B59B6,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        
        if author_icon:
            embed.set_author(name=author_name, icon_url=author_icon)
        else:
            embed.set_author(name=author_name)

        icon_file = None
        if os.path.exists("assets/hsr/hsr-icon.png"):
            icon_file = discord.File("assets/hsr/hsr-icon.png", filename="hsr-icon.png")
            embed.set_thumbnail(url="attachment://hsr-icon.png")

        # 開拓力
        stamina_full = notes.current_stamina >= notes.max_stamina
        stamina_val = (
            "⚠️ **満タン！**"
            if stamina_full
            else f"回復まで: {fmt_td(notes.stamina_recover_time)}"
        )
        reserve = getattr(notes, "current_reserve_stamina", None)
        reserve_line = f"\n{self.bot.custom_emojis.get('hsr_yobi_kaitakuryoku', '📦️')} 予備開拓力: `{reserve}`" if reserve is not None else ""
        embed.add_field(
            name=f"{self.bot.custom_emojis.get('hsr_kaitakuryoku', '⚡')} 開拓力",
            value=f"`{notes.current_stamina} / {notes.max_stamina}`\n{stamina_val}{reserve_line}",
            inline=True,
        )

        # 依頼（探索）
        accepted = getattr(notes, "accepted_expedition_num", None)
        total_exp = getattr(notes, "total_expedition_num", None)
        if notes.expeditions:
            exp_lines = []
            for exp in notes.expeditions:
                name = getattr(exp, "name", "キャラ")
                if exp.status == "Finished":
                    exp_lines.append(f"✅ {name}")
                else:
                    exp_lines.append(f"⏳ {name}（{fmt_td(exp.remaining_time)}）")
            exp_val = "\n".join(exp_lines)
            if accepted is not None and total_exp is not None:
                exp_val = f"`{accepted} / {total_exp}` 派遣中\n" + exp_val
        else:
            exp_val = "派遣なし"
        embed.add_field(name=f"{self.bot.custom_emojis.get('hsr_irai_haken', '🗺️')} 依頼（探索）", value=exp_val, inline=False)
        embed.add_field(name="​", value="​", inline=False)

        # デイリー訓練
        train_cur = getattr(notes, "current_train_score", None)
        train_max = getattr(notes, "max_train_score", None)
        if train_cur is not None and train_max is not None:
            if train_cur >= train_max:
                train_val = f"✅ 達成済み `{train_cur}/{train_max}`"
            else:
                train_val = f"⏳ `{train_cur} / {train_max}`"
        else:
            train_val = "取得不可"
        embed.add_field(name=f"{self.bot.custom_emojis.get('hsr_daily_kunren', '📋')} デイリー訓練", value=train_val, inline=True)

        # 模擬宇宙
        rogue_cur = getattr(notes, "current_rogue_score", None)
        rogue_max = getattr(notes, "max_rogue_score", None)
        if rogue_cur is not None and rogue_max is not None:
            if rogue_cur >= rogue_max:
                rogue_val = f"✅ 達成済み `{rogue_cur}/{rogue_max}`"
            else:
                rogue_val = f"⏳ `{rogue_cur} / {rogue_max}`"
        else:
            rogue_val = "取得不可"
        embed.add_field(name=f"{self.bot.custom_emojis.get('hsr_mogi_utyuu', '🌌')} 模擬宇宙", value=rogue_val, inline=True)

        embed.add_field(name="​", value="​", inline=False)

        weekly_rem = getattr(notes, "remaining_weekly_discounts", None)
        weekly_max = getattr(notes, "max_weekly_discounts", None)
        if weekly_rem is not None and weekly_max is not None:
            if weekly_rem <= 0:
                weekly_val = f"今週分は使い切りました `0/{weekly_max}`"
            else:
                weekly_val = f"残り `{weekly_rem} / {weekly_max}` 回"
        else:
            weekly_val = "取得不可"
        embed.add_field(name=f"{self.bot.custom_emojis.get('hsr_rekisen_yoin', '⚔️')} 歴戦余韻", value=weekly_val, inline=True)

        embed.set_footer(text="最終更新")
        if icon_file:
            await interaction.followup.send(embed=embed, file=icon_file)
        else:
            await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(HSRCommands(bot))
