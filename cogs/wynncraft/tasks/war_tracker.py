import logging
from datetime import datetime, timezone, timedelta

import discord
from discord.ext import commands, tasks
import libsql_client

from configs import TURSO_DATABASE_URL, TURSO_AUTH_TOKEN
from cogs.wynncraft.libs.api_stocker import WynncraftAPI

logger = logging.getLogger(__name__)

NOTIFICATION_CHANNEL_ID = 1501198030517567518
WAR_LOOKBACK_MINUTES    = 10   # move_logs を遡る最大分数
CLEANUP_INTERVAL_MIN    = 10   # move_logs クリーンアップ間隔（分）


def _utc_now_str() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')


def _parse_api_dt(s: str) -> datetime:
    """Wynncraft APIが返す acquired_at 文字列をパースする（Zサフィックス対応）"""
    return datetime.fromisoformat(s.replace('Z', '+00:00'))


def _parse_log_ts(s: str) -> datetime:
    """move_logs に保存した UTC 文字列（タイムゾーンなし）をパースする"""
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _to_sql_dt(dt: datetime) -> str:
    """datetime を SQLite 比較用の文字列に変換する"""
    return dt.strftime('%Y-%m-%dT%H:%M:%S')


class GuildWarTracker(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.api = WynncraftAPI()
        self.db: libsql_client.Client | None = None
        # {player_name: world_name} ― メモリ上のスナップショット
        self.player_snapshot: dict[str, str] = {}
        # {territory_name: {guild_name, guild_prefix, acquired_at}} ― メモリキャッシュ
        self.territory_cache: dict[str, dict] = {}

    # ------------------------------------------------------------------ #
    # Cog のライフサイクル
    # ------------------------------------------------------------------ #

    async def cog_load(self):
        if not TURSO_DATABASE_URL or not TURSO_AUTH_TOKEN:
            logger.error("TURSO_DATABASE_URL / TURSO_AUTH_TOKEN が未設定です。war_tracker を無効化します。")
            return

        db_url = TURSO_DATABASE_URL
        # WebSocket接続(libsql/wss)が環境によって失敗する場合、HTTPSにフォールバックさせる
        if db_url and db_url.startswith("libsql://"):
            db_url = "https://" + db_url[len("libsql://"):]

        self.db = libsql_client.create_client(
            url=db_url,
            auth_token=TURSO_AUTH_TOKEN,
        )
        await self._setup_db()
        await self._initial_territory_sync()

        self.player_tracker.start()
        self.territory_tracker.start()
        self.cleanup_move_logs.start()
        logger.info("GuildWarTracker が起動しました")

    async def cog_unload(self):
        self.player_tracker.cancel()
        self.territory_tracker.cancel()
        self.cleanup_move_logs.cancel()
        if self.db:
            await self.db.close()
        await self.api.close()

    # ------------------------------------------------------------------ #
    # DB 初期化
    # ------------------------------------------------------------------ #

    async def _setup_db(self):
        stmts = [
            """CREATE TABLE IF NOT EXISTS territory_status (
                territory_name TEXT PRIMARY KEY,
                guild_name     TEXT,
                guild_prefix   TEXT,
                acquired_at    TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS move_logs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                player_name TEXT NOT NULL,
                world_name  TEXT NOT NULL,
                timestamp   TEXT NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS idx_ml_player       ON move_logs(player_name)",
            "CREATE INDEX IF NOT EXISTS idx_ml_world        ON move_logs(world_name)",
            "CREATE INDEX IF NOT EXISTS idx_ml_player_world ON move_logs(player_name, world_name)",
        ]
        for stmt in stmts:
            await self.db.execute(stmt)
        logger.info("DB テーブル／インデックスのセットアップ完了")

    # ------------------------------------------------------------------ #
    # 初回起動時の領地同期（通知なし）
    # ------------------------------------------------------------------ #

    async def _initial_territory_sync(self):
        result = await self.db.execute(
            "SELECT territory_name, guild_name, guild_prefix, acquired_at FROM territory_status"
        )
        self.territory_cache = {
            row[0]: {'guild_name': row[1], 'guild_prefix': row[2], 'acquired_at': row[3]}
            for row in result.rows
        }

        if self.territory_cache:
            logger.info(f"territory_cache を DB から {len(self.territory_cache)} 件ロードしました")
            return

        logger.info("territory_status が空です。API から初期データを同期します（通知なし）。")
        territory_data = await self.api.get_territory_list()
        if not territory_data:
            logger.error("初期同期用の領地データを取得できませんでした。")
            return

        stmts = []
        for name, data in territory_data.items():
            guild       = data.get('guild') or {}
            guild_name  = guild.get('name')
            guild_prefix = guild.get('prefix')
            acquired_at = data.get('acquired')
            self.territory_cache[name] = {
                'guild_name':   guild_name,
                'guild_prefix': guild_prefix,
                'acquired_at':  acquired_at,
            }
            stmts.append(libsql_client.Statement(
                "INSERT OR IGNORE INTO territory_status "
                "(territory_name, guild_name, guild_prefix, acquired_at) VALUES (?, ?, ?, ?)",
                [name, guild_name, guild_prefix, acquired_at],
            ))

        if stmts:
            await self.db.batch(stmts)
        logger.info(f"領地データ {len(stmts)} 件を初期同期しました（通知なし）")

    # ------------------------------------------------------------------ #
    # フェーズ1：プレイヤー移動のトラッキング（15秒ごと）
    # ------------------------------------------------------------------ #

    @tasks.loop(seconds=15)
    async def player_tracker(self):
        if self.db is None:
            return
        try:
            data = await self.api.get_online_players()
            if not data:
                return

            new_snapshot: dict[str, str] = data.get('players') or {}
            now = _utc_now_str()

            # ワールドが変わったプレイヤーのみ抽出
            changed = [
                (player, world, now)
                for player, world in new_snapshot.items()
                if self.player_snapshot.get(player) != world
            ]

            if changed:
                await self.db.batch([
                    libsql_client.Statement(
                        "INSERT INTO move_logs (player_name, world_name, timestamp) VALUES (?, ?, ?)",
                        [player, world, ts],
                    )
                    for player, world, ts in changed
                ])

            self.player_snapshot = new_snapshot
        except Exception:
            logger.exception("player_tracker でエラーが発生しました")

    @player_tracker.before_loop
    async def _before_player_tracker(self):
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------------ #
    # フェーズ2：領地奪取の検知と DB 更新（15秒ごと）
    # ------------------------------------------------------------------ #

    @tasks.loop(seconds=15)
    async def territory_tracker(self):
        if self.db is None:
            return
        try:
            territory_data = await self.api.get_territory_list()
            if not territory_data:
                return

            captures:     list[dict] = []
            update_stmts: list       = []

            for territory_name, data in territory_data.items():
                guild        = data.get('guild') or {}
                new_guild_name   = guild.get('name')
                new_guild_prefix = guild.get('prefix')
                new_acquired_at  = data.get('acquired')

                if not new_guild_name:
                    continue

                cached = self.territory_cache.get(territory_name)

                if cached is None:
                    self.territory_cache[territory_name] = {
                        'guild_name':   new_guild_name,
                        'guild_prefix': new_guild_prefix,
                        'acquired_at':  new_acquired_at,
                    }
                    update_stmts.append(libsql_client.Statement(
                        "INSERT INTO territory_status "
                        "(territory_name, guild_name, guild_prefix, acquired_at) VALUES (?, ?, ?, ?)",
                        [territory_name, new_guild_name, new_guild_prefix, new_acquired_at],
                    ))

                elif cached['acquired_at'] != new_acquired_at:
                    # acquired_at が更新された ＝ 所有者が変わった
                    captures.append({
                        'territory_name':   territory_name,
                        'old_guild_name':   cached['guild_name'],
                        'old_guild_prefix': cached['guild_prefix'],
                        'new_guild_name':   new_guild_name,
                        'new_guild_prefix': new_guild_prefix,
                        'acquired_at':      new_acquired_at,
                    })
                    self.territory_cache[territory_name] = {
                        'guild_name':   new_guild_name,
                        'guild_prefix': new_guild_prefix,
                        'acquired_at':  new_acquired_at,
                    }
                    update_stmts.append(libsql_client.Statement(
                        "UPDATE territory_status "
                        "SET guild_name=?, guild_prefix=?, acquired_at=? WHERE territory_name=?",
                        [new_guild_name, new_guild_prefix, new_acquired_at, territory_name],
                    ))

            if update_stmts:
                await self.db.batch(update_stmts)

            # フェーズ3 を順次実行
            for capture in captures:
                await self._process_capture(capture)

        except Exception:
            logger.exception("territory_tracker でエラーが発生しました")

    @territory_tracker.before_loop
    async def _before_territory_tracker(self):
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------------ #
    # フェーズ3：参加者特定・Duration 計算・Discord 通知
    # ------------------------------------------------------------------ #

    async def _process_capture(self, capture: dict):
        territory_name   = capture['territory_name']
        old_guild_name   = capture['old_guild_name']
        old_guild_prefix = capture['old_guild_prefix']
        new_guild_name   = capture['new_guild_name']
        new_guild_prefix = capture['new_guild_prefix']
        acquired_at_str  = capture['acquired_at']

        try:
            acquired_at = _parse_api_dt(acquired_at_str)
        except Exception:
            logger.exception(f"acquired_at のパース失敗: {acquired_at_str!r}")
            acquired_at = datetime.now(timezone.utc)

        logger.info(
            f"領地奪取を検知: {territory_name} → {new_guild_name} [{new_guild_prefix}]"
            f" at {acquired_at_str}"
        )

        # territory_cache は既にこの奪取を反映して更新済みなので、
        # そのまま集計すれば「変更があった時点での」領地数になる
        old_tc = sum(1 for v in self.territory_cache.values() if v['guild_name'] == old_guild_name)
        new_tc = sum(1 for v in self.territory_cache.values() if v['guild_name'] == new_guild_name)

        # Guild API は「新しく取得したギルド」に対してのみ 1 回実行
        guild_data = await self.api.get_guild_by_name(new_guild_name)
        if not guild_data:
            logger.warning(f"ギルドデータ取得失敗: {new_guild_name!r}")
            await self._send_notification(
                territory_name,
                old_guild_name, old_guild_prefix, old_tc,
                new_guild_name, new_guild_prefix, new_tc,
                acquired_at, war_world=None, participants=[], duration_seconds=None,
            )
            return

        # ギルドメンバー全員の名前を収集
        member_names: list[str] = []
        members_section = guild_data.get('members') or {}
        for rank, rank_members in members_section.items():
            if rank == 'total':
                continue
            if isinstance(rank_members, dict):
                member_names.extend(rank_members.keys())

        if not member_names:
            logger.warning(f"メンバーが見つかりません: {new_guild_name!r}")
            await self._send_notification(
                territory_name,
                old_guild_name, old_guild_prefix, old_tc,
                new_guild_name, new_guild_prefix, new_tc,
                acquired_at, war_world=None, participants=[], duration_seconds=None,
            )
            return

        # move_logs を遡る期間
        lookback_dt  = acquired_at - timedelta(minutes=WAR_LOOKBACK_MINUTES)
        lookback_str = _to_sql_dt(lookback_dt)
        acq_str      = _to_sql_dt(acquired_at)
        ph           = ','.join('?' for _ in member_names)

        # ウォーワールドを推定：メンバーが最も多く移動したワールドを採用
        world_rs = await self.db.execute(libsql_client.Statement(
            f"SELECT world_name, COUNT(DISTINCT player_name) AS cnt "
            f"FROM move_logs "
            f"WHERE player_name IN ({ph}) AND timestamp >= ? AND timestamp <= ? "
            f"GROUP BY world_name ORDER BY cnt DESC LIMIT 1",
            member_names + [lookback_str, acq_str],
        ))

        if not world_rs.rows:
            logger.warning(f"ウォーワールドを特定できませんでした: {territory_name!r}")
            await self._send_notification(
                territory_name,
                old_guild_name, old_guild_prefix, old_tc,
                new_guild_name, new_guild_prefix, new_tc,
                acquired_at, war_world=None, participants=[], duration_seconds=None,
            )
            return

        war_world = world_rs.rows[0][0]

        # 参加プレイヤーを抽出（ウォーワールドに移動記録があるメンバー）
        participants_rs = await self.db.execute(libsql_client.Statement(
            f"SELECT player_name, MIN(timestamp) AS earliest_move "
            f"FROM move_logs "
            f"WHERE player_name IN ({ph}) "
            f"  AND world_name = ? AND timestamp >= ? AND timestamp <= ? "
            f"GROUP BY player_name",
            member_names + [war_world, lookback_str, acq_str],
        ))

        participants:    list[str] = []
        earliest_times:  list[str] = []
        for row in participants_rs.rows:
            participants.append(row[0])
            earliest_times.append(row[1])

        # T_Jump と Duration を計算
        duration_seconds: float | None = None
        try:
            if earliest_times:
                t_jump = min(_parse_log_ts(t) for t in earliest_times)
                raw    = (acquired_at - t_jump).total_seconds() - 25
                duration_seconds = max(raw, 0.0)
        except Exception:
            logger.exception("Duration の算出中にエラーが発生しました")

        await self._send_notification(
            territory_name,
            old_guild_name, old_guild_prefix, old_tc,
            new_guild_name, new_guild_prefix, new_tc,
            acquired_at, war_world, participants, duration_seconds,
        )

    # ------------------------------------------------------------------ #
    # Discord Embed 通知
    # ------------------------------------------------------------------ #

    async def _send_notification(
        self,
        territory_name:    str,
        old_guild_name:    str | None,
        old_guild_prefix:  str | None,
        old_territory_count: int,
        new_guild_name:    str,
        new_guild_prefix:  str,
        new_territory_count: int,
        acquired_at:       datetime,
        war_world:         str | None,
        participants:      list[str],
        duration_seconds:  float | None,
    ):
        channel = self.bot.get_channel(NOTIFICATION_CHANNEL_ID)
        if channel is None:
            logger.error(f"通知チャンネルが見つかりません: {NOTIFICATION_CHANNEL_ID}")
            return

        embed = discord.Embed(
            title=f"⛳️ 領地が取得されました",
            description=f"**{territory_name}**",
            color=discord.Color.blue(),
            timestamp=acquired_at,
        )

        old_part = (
            f"{old_guild_name} `[{old_guild_prefix}]` ({old_territory_count})"
            if old_guild_name else "不明"
        )
        embed.add_field(
            name="所有ギルド",
            value=f"{old_part} → **{new_guild_name}** `[{new_guild_prefix}]` ({new_territory_count})",
            inline=False,
        )

        if duration_seconds is not None:
            m, s = divmod(int(duration_seconds), 60)
            duration_str = f"{m}分 {s}秒"
        else:
            duration_str = "算出不能"
        embed.add_field(name="推定戦闘時間", value=duration_str, inline=True)

        embed.add_field(
            name="戦闘ワールド",
            value=war_world if war_world else "特定できませんでした",
            inline=True,
        )

        if participants:
            # Guild War は最大 5 人なので 5 人までに制限
            capped = participants[:5]
            # アンダーバーを \_  にエスケープして Discord のイタリック化を防ぐ
            escaped = [p.replace('_', r'\_') for p in capped]
            embed.add_field(
                name=f"参加プレイヤー ({len(capped)}名)",
                value=', '.join(escaped),
                inline=False,
            )
        else:
            embed.add_field(name="参加プレイヤー", value="特定できませんでした", inline=False)

        try:
            await channel.send(embed=embed)
        except Exception:
            logger.exception("Embed の送信に失敗しました")

    # ------------------------------------------------------------------ #
    # 定期クリーンアップ：1時間以上前の move_logs を削除
    # ------------------------------------------------------------------ #

    @tasks.loop(minutes=CLEANUP_INTERVAL_MIN)
    async def cleanup_move_logs(self):
        if self.db is None:
            return
        try:
            await self.db.execute(
                "DELETE FROM move_logs WHERE timestamp < datetime('now', '-1 hour')"
            )
            logger.debug("古い移動ログを削除しました")
        except Exception:
            logger.exception("move_logs クリーンアップ中にエラーが発生しました")

    @cleanup_move_logs.before_loop
    async def _before_cleanup(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(GuildWarTracker(bot))
