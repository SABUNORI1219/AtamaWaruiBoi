from PIL import Image, ImageDraw, ImageFont, ImageFilter
from io import BytesIO
import logging
import os

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
FONT_PATH = os.path.join(PROJECT_ROOT, "assets/wynncraft/fonts/Minecraftia-Regular.ttf")
BASE_IMG_PATH = os.path.join(PROJECT_ROOT, "assets/wynncraft/player_profile/profile_card_template.png")
PLAYER_BACKGROUND_PATH = os.path.join(PROJECT_ROOT, "assets/wynncraft/player_profile/background.png")
RANK_STAR_PATH = os.path.join(PROJECT_ROOT, "assets/wynncraft/player_profile/rankStar.png")
UNKNOWN_SKIN_PATH = os.path.join(PROJECT_ROOT, "assets/wynncraft/player_profile/unknown_skin.png")

def gradient_rect(size, color_top, color_bottom, radius):
    w, h = size
    base = Image.new("RGBA", (w, h), (0,0,0,0))
    for y in range(h):
        ratio = y / h
        r = int(color_top[0] * (1-ratio) + color_bottom[0] * ratio)
        g = int(color_top[1] * (1-ratio) + color_bottom[1] * ratio)
        b = int(color_top[2] * (1-ratio) + color_bottom[2] * ratio)
        a = int(color_top[3] * (1-ratio) + color_bottom[3] * ratio)
        ImageDraw.Draw(base).line([(0, y), (w, y)], fill=(r, g, b, a))
    mask = Image.new("L", (w, h), 0)
    draw_mask = ImageDraw.Draw(mask)
    draw_mask.rounded_rectangle([0, 0, w, h], radius=radius, fill=255)
    base.putalpha(mask)
    return base

def resize_icon_keep_ratio(img, target_height):
    w, h = img.size
    scale = target_height / h
    target_w = int(w * scale)
    return img.resize((target_w, target_height), Image.LANCZOS)

def fmt_num(val):
    if isinstance(val, int) or isinstance(val, float):
        return f"{val:,}"
    return str(val)

def fmt_short(val):
    try:
        if val in ("???", "N/A", None):
            return str(val) if val else "0"
        num = float(val)
    except (ValueError, TypeError):
        return str(val) if val else "0"
        
    if num >= 1_000_000_000:
        return f"{num / 1_000_000_000:.1f}B".replace(".0B", "B")
    elif num >= 1_000_000:
        return f"{num / 1_000_000:.1f}M".replace(".0M", "M")
    elif num >= 1_000:
        return f"{num / 1_000:.1f}K".replace(".0K", "K")
    else:
        return f"{int(num):,}"

def split_guild_name_by_pixel_and_word(guild_name, font, text_base_x, threshold_x, draw):
    words = guild_name.split()
    if text_base_x + draw.textlength(guild_name, font=font) <= threshold_x:
        return [guild_name]
    # 2単語以上なら均等分割
    if len(words) > 1:
        best_split = 1
        min_diff = float('inf')
        for i in range(1, len(words)):
            line1 = " ".join(words[:i])
            line2 = " ".join(words[i:])
            l1_len = draw.textlength(line1, font=font)
            l2_len = draw.textlength(line2, font=font)
            diff = abs(l1_len - l2_len)
            if diff < min_diff:
                min_diff = diff
                best_split = i
        return [" ".join(words[:best_split]), " ".join(words[best_split:])]
    else:
        # 1単語しかない場合は強制分割
        text = words[0]
        for i in range(1, len(text)):
            part1 = text[:i]
            part2 = text[i:]
            if text_base_x + draw.textlength(part1, font=font) > threshold_x:
                return [part1, part2]
        return [text]

def draw_status_circle(base_img, left_x, center_y, status="online"):
    circle_radius = 15
    circle_img = Image.new("RGBA", (2*circle_radius, 2*circle_radius), (0,0,0,0))
    draw = ImageDraw.Draw(circle_img)

    for r in range(circle_radius, 0, -1):
        ratio = r / circle_radius
        if status == "online":
            col = (
                int(60 + 140 * ratio),
                int(230 - 60 * ratio),
                int(60 + 20 * ratio),
                255
            )
        else:
            col = (
                int(220 - 40 * ratio),
                int(60 + 40 * ratio),
                int(60 + 40 * ratio),
                255
            )
        draw.ellipse([circle_radius-r, circle_radius-r, circle_radius+r, circle_radius+r], fill=col)

    if status == "online":
        outline_color = (16, 100, 16, 255)
    else:
        outline_color = (180, 32, 32, 255)
    draw.ellipse([0, 0, 2*circle_radius-1, 2*circle_radius-1], outline=outline_color, width=2)

    base_img.alpha_composite(circle_img, (left_x, center_y - circle_radius))

def generate_profile_card(info, output_path="profile_card.png", skin_image=None):
    img = None
    PLAYER_BACKGROUND = None
    rank_star_img = None
    guild_banner_img = None
    dummy = None
    try:
        with Image.open(BASE_IMG_PATH) as base_img:
            img = base_img.convert("RGBA")
    except Exception as e:
        logger.error(f"BASE_IMG_PATH 読み込み失敗: {e}")
        img = Image.new("RGBA", (900, 1600), (255, 255, 255, 255))
    try:
        with Image.open(PLAYER_BACKGROUND_PATH) as bg_img:
            PLAYER_BACKGROUND = bg_img.convert("RGBA")
            # テンプレートの枠に合わせてサイズを強制的に変更する (幅, 高さ)
            PLAYER_BACKGROUND = PLAYER_BACKGROUND.resize((221, 253), Image.LANCZOS)
    except Exception as e:
        logger.error(f"PLAYER_BACKGROUND_PATH 読み込み失敗: {e}")
        PLAYER_BACKGROUND = Image.new("RGBA", (221, 253), (200, 200, 200, 255))
    try:
        with Image.open(RANK_STAR_PATH) as star_img:
            rank_star_img = star_img.convert("RGBA")
    except Exception as e:
        logger.error(f"RANK_STAR_PATH 読み込み失敗: {e}")
        rank_star_img = Image.new("RGBA", (200, 200), (200, 200, 200, 255))
    draw = ImageDraw.Draw(img)
    W, H = img.size
    star_size = 50
    rank_star_img = rank_star_img.resize((star_size, star_size), Image.LANCZOS)

    # フォント設定
    try:
        font_title = ImageFont.truetype(FONT_PATH, 50)
        font_main = ImageFont.truetype(FONT_PATH, 45)
        font_sub = ImageFont.truetype(FONT_PATH, 42)
        font_raids = ImageFont.truetype(FONT_PATH, 35)
        font_uuid = ImageFont.truetype(FONT_PATH, 30)
        font_mini = ImageFont.truetype(FONT_PATH, 25)
        font_tiny = ImageFont.truetype(FONT_PATH, 21)
        font_vtiny = ImageFont.truetype(FONT_PATH, 18)
        font_prefix = ImageFont.truetype(FONT_PATH, 12)
    except Exception as e:
        logger.error(f"FONT_PATH 読み込み失敗: {e}")
        font_title = font_main = font_sub = font_small = font_uuid = font_mini = font_prefix = font_rank = ImageFont.load_default()

    rank_text = info.get('support_rank')
    rank_img_path = None
    if rank_text:
        rank_lower = rank_text.lower()
        if rank_lower == "champion":
            rank_img_path = os.path.join(PROJECT_ROOT, "assets/wynncraft/player_profile/CHAMPION.png")
        elif rank_lower == "heroplus":
            rank_img_path = os.path.join(PROJECT_ROOT, "assets/wynncraft/player_profile/HERO+.png")
        elif rank_lower == "hero":
            rank_img_path = os.path.join(PROJECT_ROOT, "assets/wynncraft/player_profile/HERO.png")
        elif rank_lower == "vipplus":
            rank_img_path = os.path.join(PROJECT_ROOT, "assets/wynncraft/player_profile/VIP+.png")
        elif rank_lower == "vip":
            rank_img_path = os.path.join(PROJECT_ROOT, "assets/wynncraft/player_profile/VIP.png")

    name_start_x = 95
    name_y = 120
    username = info.get('username', 'No Name')

    if rank_img_path and os.path.exists(rank_img_path):
        try:
            with Image.open(rank_img_path) as original_rank_img:
                rank_rgba = original_rank_img.convert("RGBA")
                orig_w, orig_h = rank_rgba.size
                rank_w, rank_h = orig_w * 2, orig_h * 2
                rank_rgba = rank_rgba.resize((rank_w, rank_h), Image.LANCZOS)
                bbox_name = draw.textbbox((0, 0), username, font=font_title)
                name_h = bbox_name[3] - bbox_name[1]
                rank_paste_y = name_y + (name_h // 2) - (rank_h // 2)
                img.paste(rank_rgba, (name_start_x, rank_paste_y), mask=rank_rgba)
                name_start_x += rank_w + 14
        except Exception as e:
            logger.error(f"Rank image load failed: {e}")

    draw.text((name_start_x, name_y+10), username, font=font_sub, fill=(60,40,30,255))

    banner_bytes = info.get("banner_bytes")
    guild_banner_img = None
    if banner_bytes and isinstance(banner_bytes, BytesIO):
        try:
            with Image.open(banner_bytes) as banner_img:
                guild_banner_img = banner_img.convert("RGBA")
        except Exception as e:
            logger.error(f"guild_banner_img読み込み失敗: {e}")
            guild_banner_img = None
    elif banner_bytes and isinstance(banner_bytes, str):
        guild_banner_img = None

    banner_x = 340
    banner_y = 210
    banner_size = (76, 150)
    if guild_banner_img:
        guild_banner_img = guild_banner_img.resize(banner_size, Image.LANCZOS)
        img.paste(guild_banner_img, (banner_x, banner_y), mask=guild_banner_img)
    else:
        dummy = Image.new("RGBA", banner_size, (0, 0, 0, 0))
        img.paste(dummy, (banner_x, banner_y), mask=dummy)

    guild_prefix = info.get('guild_prefix', '')
    guild_name = info.get('guild_name', '')
    if not guild_name or guild_name == "Hidden":
        guild_name_display = "No Guild"
    else:
        guild_name_display = guild_name
        
    if guild_prefix:
        prefix_text = guild_prefix
        prefix_font = font_prefix
        bbox = draw.textbbox((0,0), prefix_text, font=prefix_font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        padding_x = 6
        padding_y = 2
        box_w = text_w + padding_x * 2
        box_h = text_h + padding_y * 2
        box_x = banner_x + (banner_size[0] - box_w) // 2
        box_y = banner_y + banner_size[1] - int(box_h * 0.4)
        shadow = Image.new("RGBA", (box_w+8, box_h+8), (0,0,0,0))
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_draw.rounded_rectangle([4,4,box_w+4,box_h+4], radius=16, fill=(0,0,0,80))
        shadow = shadow.filter(ImageFilter.GaussianBlur(3))
        img.paste(shadow, (box_x-4, box_y-4), mask=shadow)
        rect_img = gradient_rect((box_w, box_h), (30,30,30,220), (60,60,60,160), radius=14)
        img.paste(rect_img, (box_x, box_y), mask=rect_img)
        text_x = box_x + (box_w - text_w) // 2
        text_y = box_y + (box_h - text_h) // 2
        draw.text((text_x, text_y), prefix_text, font=prefix_font, fill=(240,240,240,255))
        
    # 背景の貼り付け (X座標, Y座標)
    bg_paste_x, bg_paste_y = 95, 225
    img.paste(PLAYER_BACKGROUND, (bg_paste_x, bg_paste_y), mask=PLAYER_BACKGROUND)
    if skin_image:
        try:
            skin = skin_image.resize((196, 196), Image.LANCZOS)
            img.paste(skin, (110, 280), mask=skin)
        except Exception as e:
            logger.error(f"Skin image process failed: {e}")
            # fallback
            try:
                with Image.open(UNKNOWN_SKIN_PATH) as unknown_img:
                    unknown_skin = unknown_img.convert("RGBA")
                    unknown_skin = unknown_skin.resize((196, 196), Image.LANCZOS)
                    img.paste(unknown_skin, (106, 340), mask=unknown_skin)
            except Exception as ee:
                logger.error(f"Unknown skin image load failed: {ee}")
    else:
        logger.error("Skin image not available")
        # fallback
        try:
            with Image.open(UNKNOWN_SKIN_PATH) as unknown_img:
                unknown_skin = unknown_img.convert("RGBA")
                unknown_skin = unknown_skin.resize((196, 196), Image.LANCZOS)
                img.paste(unknown_skin, (106, 340), mask=unknown_skin)
        except Exception as ee:
            logger.error(f"Unknown skin image load failed: {ee}")

    text_base_x = banner_x + banner_size[0] + 10
    guild_name_lines = split_guild_name_by_pixel_and_word(guild_name_display, font_main, text_base_x, 975, draw)
    if len(guild_name_lines) == 1:
        draw.text((text_base_x, banner_y), guild_name_lines[0], font=font_main, fill=(60,40,30,255))
    else:
        try:
            font_guild_small = ImageFont.truetype(FONT_PATH, 33)
        except Exception:
            font_guild_small = ImageFont.load_default()
        draw.text((text_base_x, banner_y), guild_name_lines[0], font=font_guild_small, fill=(60,40,30,255))
        draw.text((text_base_x, banner_y + 33 + 5), guild_name_lines[1], font=font_guild_small, fill=(60,40,30,255))
        banner_y += 10

    guild_rank_text = str(info.get('guild_rank', ''))
    star_num = 0
    if guild_rank_text == "OWNER":
        star_num = 5
    elif guild_rank_text == "CHIEF":
        star_num = 4
    elif guild_rank_text == "STRATEGIST":
        star_num = 3
    elif guild_rank_text == "CAPTAIN":
        star_num = 2
    elif guild_rank_text == "RECRUITER":
        star_num = 1
    draw.text((text_base_x, banner_y + 75), f"{guild_rank_text}", font=font_main, fill=(60,40,30,255))
    bbox = draw.textbbox((text_base_x, banner_y + 75), f"{guild_rank_text}", font=font_main)
    x_grank = bbox[2] + 10
    y_star = banner_y + 80
    for i in range(star_num):
        x = x_grank + i * (star_size)
        img.paste(rank_star_img, (x, y_star), mask=rank_star_img)

    server_display = info.get('server_display', 'Unknown')
    active_char_info = info.get('active_char_info', 'Unknown')
    # 左側にステータス丸（オンライン：緑、オフライン：赤）を描画
    status_circle_x = 340
    status_circle_y = 365 + 35
    text_x = status_circle_x + 45
    text_y = 370
    if not server_display.lower() == "offline":
        draw_status_circle(img, status_circle_x, status_circle_y, status="online")
    else:
        draw_status_circle(img, status_circle_x, status_circle_y, status="offline")
    draw.text((text_x, text_y), f"{server_display}", font=font_main, fill=(60,40,30,255))
    draw.text((340, text_y+65), f"Class: {active_char_info}", font=font_main, fill=(60,40,30,255))

    draw.text((70, 520), "Total Level:", font=font_mini, fill=(60,40,30,255))
    total_text = fmt_num(info.get('total_level', 0))
    bbox_lv = draw.textbbox((0, 0), "lv.", font=font_prefix)
    lv_width = bbox_lv[2] - bbox_lv[0]
    x_lv = 355 - lv_width
    draw.text((x_lv, 565), "lv.", font=font_prefix, fill=(60,40,30,255))
    bbox_total = draw.textbbox((0, 0), total_text, font=font_mini)
    total_width = bbox_total[2] - bbox_total[0]
    draw.text((x_lv - 3 - total_width, 550), total_text, font=font_mini, fill=(60,40,30,255))

    draw.text((70, 590), "Dungeons:", font=font_mini, fill=(60,40,30,255))
    dun_text = fmt_num(info.get('dungeons', 0))
    bbox_dun = draw.textbbox((0, 0), dun_text, font=font_mini)
    draw.text((355 - (bbox_dun[2] - bbox_dun[0]), 620), dun_text, font=font_mini, fill=(60,40,30,255))

    draw.text((70, 660), "World Events:", font=font_mini, fill=(60,40,30,255))
    we_text = fmt_num(info.get('world_events', 0))
    bbox_we = draw.textbbox((0, 0), we_text, font=font_mini)
    draw.text((355 - (bbox_we[2] - bbox_we[0]), 690), we_text, font=font_mini, fill=(60,40,30,255))

    draw.text((70, 730), "Caves:", font=font_mini, fill=(60,40,30,255))
    caves_text = fmt_num(info.get('caves', 0))
    bbox_caves = draw.textbbox((0, 0), caves_text, font=font_mini)
    draw.text((355 - (bbox_caves[2] - bbox_caves[0]), 730), caves_text, font=font_mini, fill=(60,40,30,255))

    draw.text((70, 770), "Quests:", font=font_mini, fill=(60,40,30,255))
    quests_text = fmt_num(info.get('quests', 0))
    bbox_quests = draw.textbbox((0, 0), quests_text, font=font_mini)
    draw.text((355 - (bbox_quests[2] - bbox_quests[0]), 770), quests_text, font=font_mini, fill=(60,40,30,255))

    draw.text((375, 520), "PvP Score:", font=font_mini, fill=(60,40,30,255))
    pk_text = fmt_num(info.get('pvp_kill', 0))
    pd_text = fmt_num(info.get('pvp_death', 0))
    pvp_val_text = f"{pk_text} K / {pd_text} D"
    bbox_pvp = draw.textbbox((0, 0), pvp_val_text, font=font_mini)
    draw.text((670 - (bbox_pvp[2] - bbox_pvp[0]), 550), pvp_val_text, font=font_mini, fill=(60,40,30,255))

    draw.text((375, 590), "Mobs Killed:", font=font_mini, fill=(60,40,30,255))
    mob_text = fmt_num(info.get('mobs_killed', 0))
    bbox_mob = draw.textbbox((0, 0), mob_text, font=font_mini)
    draw.text((670 - (bbox_mob[2] - bbox_mob[0]), 620), mob_text, font=font_mini, fill=(60,40,30,255))

    draw.text((375, 660), "Chests Opened:", font=font_mini, fill=(60,40,30,255))
    chest_text = fmt_num(info.get('chests', 0))
    bbox_chest = draw.textbbox((0, 0), chest_text, font=font_mini)
    draw.text((670 - (bbox_chest[2] - bbox_chest[0]), 690), chest_text, font=font_mini, fill=(60,40,30,255))

    draw.text((375, 730), "Wars Done:", font=font_mini, fill=(60,40,30,255))
    wars_done_text = fmt_num(info.get('wars', 0))
    bbox_wars_done = draw.textbbox((0, 0), wars_done_text, font=font_mini)
    draw.text((670 - (bbox_wars_done[2] - bbox_wars_done[0]), 730), wars_done_text, font=font_mini, fill=(60,40,30,255))

    draw.text((375, 770), "War Rank:", font=font_mini, fill=(60,40,30,255))
    war_rank_val = info.get('war_rank_display', 'N/A')
    if war_rank_val not in ("N/A", "非公開", None):
        try:
            war_rank_text = f"#{fmt_num(int(war_rank_val))}"
        except (ValueError, TypeError):
            war_rank_text = f"#{war_rank_val}"
    else:
        war_rank_text = str(war_rank_val) if war_rank_val else "N/A"
    bbox_war_rank = draw.textbbox((0, 0), war_rank_text, font=font_mini)
    draw.text((670 - (bbox_war_rank[2] - bbox_war_rank[0]), 770), war_rank_text, font=font_mini, fill=(60,40,30,255))

    draw.text((690, 520), "First Join:", font=font_mini, fill=(60,40,30,255))
    fj_text = f"{info.get('first_join', 'N/A')}"
    bbox_fj = draw.textbbox((0, 0), fj_text, font=font_tiny)
    fj_width = bbox_fj[2] - bbox_fj[0]
    draw.text((975 - fj_width, 555), fj_text, font=font_tiny, fill=(60,40,30,255))

    draw.text((690, 590), "Last Seen:", font=font_mini, fill=(60,40,30,255))
    lj_text = f"{info.get('last_join', 'N/A')}"
    bbox_lj = draw.textbbox((0, 0), lj_text, font=font_tiny)
    lj_width = bbox_lj[2] - bbox_lj[0]
    draw.text((975 - lj_width, 625), lj_text, font=font_tiny, fill=(60,40,30,255))

    draw.text((690, 660), "Playtime:", font=font_mini, fill=(60,40,30,255))
    playtime_text = fmt_num(info.get('playtime', 0))
    bbox_hours = draw.textbbox((0, 0), "hours", font=font_prefix)
    hours_width = bbox_hours[2] - bbox_hours[0]
    x_hours = 975 - hours_width
    draw.text((x_hours, 705), "hours", font=font_prefix, fill=(60,40,30,255))
    bbox_playtime = draw.textbbox((0, 0), playtime_text, font=font_mini)
    playtime_width = bbox_playtime[2] - bbox_playtime[0]
    draw.text((x_hours - 3 - playtime_width, 690), playtime_text, font=font_mini, fill=(60,40,30,255))

    raid_stat_y = 900
    draw.text((70, 845), "Raid Completions", font=font_raids, fill=(90,60,30,255))
    draw.text((70, raid_stat_y), "Content", font=font_mini, fill=(60,40,30,255))
    draw.text((245, raid_stat_y), "Total", font=font_mini, fill=(60,40,30,255))
    draw.text((350, raid_stat_y), "Rank", font=font_mini, fill=(60,40,30,255))
    draw.text((440, raid_stat_y), "Normal", font=font_mini, fill=(60,40,30,255))
    draw.text((560, raid_stat_y), "Guild", font=font_mini, fill=(60,40,30,255))

    total_right_edge_x = 323
    rank_right_edge_x = 430
    normal_left_x = 440
    graid_right_edge_x = 633

    raid_keys = [
        ("NOTG", "notg", "graid_notg", 'notg_rank_display', 938),
        ("NOL", "nol", "graid_nol", 'nol_rank_display', 977),
        ("TCC", "tcc", "graid_tcc", 'tcc_rank_display', 1016),
        ("TNA", "tna", "graid_tna", 'tna_rank_display', 1055),
        ("TWP", "twp", "graid_twp", 'twp_rank_display', 1094),
        ("Total", "all_raids", "all_guild_raids", None, 1133)
    ]

    for label, t_key, g_key, r_key, y in raid_keys:
        draw.text((70, y), label, font=font_mini, fill=(60,40,30,255))
        
        t_val = info.get(t_key, 0)
        g_val = info.get(g_key, 0)
        
        t_text = fmt_num(t_val)
        bbox = draw.textbbox((0,0), t_text, font=font_mini)
        t_w = bbox[2] - bbox[0]
        draw.text((total_right_edge_x - t_w, y), t_text, font=font_mini, fill=(60,40,30,255))
        
        if r_key:
            rank_val = info.get(r_key, 'N/A')
            if rank_val not in ("N/A", "非公開", None):
                try:
                    rank_text = f"#{fmt_num(int(rank_val))}"
                except (ValueError, TypeError):
                    rank_text = f"#{rank_val}"
            else:
                rank_text = str(rank_val) if rank_val else "N/A"
            
            bbox = draw.textbbox((0, 0), rank_text, font=font_vtiny)
            r_w = bbox[2] - bbox[0]
            draw.text((rank_right_edge_x - r_w, y+5), rank_text, font=font_vtiny, fill=(60,40,30,255))
            
        try:
            n_val = max(0, int(t_val) - int(g_val))
        except (ValueError, TypeError):
            n_val = t_val
            
        n_text = fmt_num(n_val)
        draw.text((normal_left_x, y), n_text, font=font_mini, fill=(60,40,30,255))

        g_text = fmt_num(g_val)
        bbox = draw.textbbox((0,0), g_text, font=font_mini)
        g_w = bbox[2] - bbox[0]
        draw.text((graid_right_edge_x - g_w, y), g_text, font=font_mini, fill=(60,40,30,255))

    
    raid_stats_y = 840
    draw.text((660, raid_stats_y), "Raid Stats", font=font_raids, fill=(90,60,30,255))
    
    raid_stats_list = [
        ("Damage Dealt", info.get("damageDealt", 0), 660, 890),
        ("Damage Taken", info.get("damageTaken", 0), 660, 930),
        ("Health Healed", info.get("healthHealed", 0), 660, 970),
        ("Deaths", info.get("deaths", 0), 660, 1010),
        ("Buffs Taken", info.get("buffsTaken", 0), 660, 1050),
        ("Gambits Used", info.get("gambitsUsed", 0), 660, 1090),
    ]

    for label, val, x, y in raid_stats_list:
        draw.text((x, y), label, font=font_mini, fill=(60,40,30,255))
        val_str = fmt_short(val)
        bbox = draw.textbbox((0, 0), val_str, font=font_mini)
        val_w = bbox[2] - bbox[0]
        draw.text((x + 320 - val_w, y), val_str, font=font_mini, fill=(60,40,30,255))

    top_ranks = info.get("top_ranks", [])
    rank_base_x = 70
    rank_base_y = 1180
    draw.text((rank_base_x, rank_base_y), "Top Ranks", font=font_raids, fill=(90, 60, 30, 255))
    
    if top_ranks:
        for i, rank_data in enumerate(top_ranks):
            y_pos = rank_base_y + 55 + (i * 70)
            draw.text((rank_base_x-10, y_pos), f"{rank_data['category']}:", font=font_tiny, fill=(60, 40, 30, 255))
            
            rank_str = f"#{fmt_num(rank_data['rank'])}"
            bbox = draw.textbbox((0,0), rank_str, font=font_tiny)
            draw.text((355 - (bbox[2] - bbox[0]), y_pos + 30), rank_str, font=font_tiny, fill=(60, 40, 30, 255))
    else:
        draw.text((rank_base_x, rank_base_y + 45), "API Hidden", font=font_uuid, fill=(60, 40, 30, 255))

    top_logins = info.get("top_logins", [])
    login_base_x = 370
    login_base_y = 1185
    draw.text((login_base_x, login_base_y), "Most Logined", font=font_uuid, fill=(90, 60, 30, 255))
    draw.text((login_base_x+155, login_base_y+40), "Classes", font=font_uuid, fill=(90, 60, 30, 255))
    
    if top_logins:
        for i, login_data in enumerate(top_logins):
            y_pos = login_base_y + 90 + (i * 70)
            draw.text((login_base_x+5, y_pos), f"{login_data['class_name']}:", font=font_tiny, fill=(60, 40, 30, 255))
            
            login_str = f"{fmt_num(login_data['logins'])}"
            bbox = draw.textbbox((0,0), login_str, font=font_tiny)
            draw.text((675 - (bbox[2] - bbox[0]), y_pos + 30), login_str, font=font_tiny, fill=(60, 40, 30, 255))
    else:
        draw.text((login_base_x, login_base_y + 75), "API Hidden", font=font_uuid, fill=(60, 40, 30, 255))

    uuid = info.get("uuid", "")
    if uuid and '-' in uuid:
        parts = uuid.split('-')
        if len(parts) == 5:
            line1 = f"{parts[0]}-{parts[1]}"
            line2 = f"{parts[2]}-{parts[3]}-"
            line3 = f"{parts[4]}"
        else:
            line1 = uuid
            line2 = ""
            line3 = ""
    else:
        line1 = line2 = ""
    draw.text((690, 1185), "UUID", font=font_uuid, fill=(90,90,90,255))
    draw.text((690, 1230), line1 + "-", font=font_tiny, fill=(90,90,90,255))
    draw.text((690, 1260), line2, font=font_tiny, fill=(90,90,90,255))
    draw.text((690, 1290), line3, font=font_tiny, fill=(90,90,90,255))
    draw.text((690, 1380), "Generated by", font=font_mini, fill=(60,40,30,255))
    draw.text((730, 1410), "AtamaWaruiBoi", font=font_mini, fill=(60,40,30,255))
    draw.text((885, 1440), "#3244", font=font_mini, fill=(60,40,30,255))

    try:
        img.save(output_path)
    except Exception as e:
        logger.error(f"画像保存失敗: {e}")
    return output_path
