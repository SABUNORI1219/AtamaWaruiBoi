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
        font_sub = ImageFont.truetype(FONT_PATH, 43)
        font_small = ImageFont.truetype(FONT_PATH, 40)
        font_raids = ImageFont.truetype(FONT_PATH, 35)
        font_uuid = ImageFont.truetype(FONT_PATH, 30)
        font_mini = ImageFont.truetype(FONT_PATH, 25)
        font_tiny = ImageFont.truetype(FONT_PATH, 22)
        font_prefix = ImageFont.truetype(FONT_PATH, 12)
    except Exception as e:
        logger.error(f"FONT_PATH 読み込み失敗: {e}")
        font_title = font_main = font_sub = font_small = font_uuid = font_mini = font_prefix = font_rank = ImageFont.load_default()

    draw.text((95, 120), f"{info.get('username', 'No Name')}", font=font_title, fill=(60,40,30,255))

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

    if rank_img_path and os.path.exists(rank_img_path):
        try:
            with Image.open(rank_img_path) as original_rank_img:
                rank_rgba = original_rank_img.convert("RGBA")
                orig_w, orig_h = rank_rgba.size
                
                # 2倍にリサイズ
                rank_w, rank_h = orig_w * 2, orig_h * 2
                rank_rgba = rank_rgba.resize((rank_w, rank_h), Image.LANCZOS)
                
                skin_x, skin_y, skin_w, skin_h = 106, 336, 196, 196
                rank_paste_x = skin_x + (skin_w // 2) - (rank_w // 2)
                rank_paste_y = skin_y + skin_h - 70
                
                img.paste(rank_rgba, (rank_paste_x, rank_paste_y), mask=rank_rgba)
        except Exception as e:
            logger.error(f"Rank image load failed: {e}")

    text_base_x = banner_x + banner_size[0] + 10
    guild_name_lines = split_guild_name_by_pixel_and_word(guild_name_display, font_main, text_base_x, 1000, draw)
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
    status_circle_y = 375 + 35
    text_x = status_circle_x + 45
    text_y = 375
    if not server_display.lower() == "offline":
        draw_status_circle(img, status_circle_x, status_circle_y, status="online")
    else:
        draw_status_circle(img, status_circle_x, status_circle_y, status="offline")
    draw.text((text_x, text_y), f"{server_display}", font=font_main, fill=(60,40,30,255))
    draw.text((340, text_y+60), f"Class: {active_char_info}", font=font_main, fill=(60,40,30,255))

    draw.text((70, 520), "Total Level:", font=font_mini, fill=(60,40,30,255))
    total_text = fmt_num(info.get('total_level', 0))
    bbox_total = draw.textbbox((0, 0), total_text, font=font_mini)
    total_width = bbox_total[2] - bbox_total[0]
    draw.text((340 - total_width, 550), total_text, font=font_mini, fill=(60,40,30,255))
    draw.text((340 + 3, 540), "lv.", font=font_prefix, fill=(60,40,30,255))

    draw.text((70, 590), "Dungeons", font=font_mini, fill=(60,40,30,255))
    dun_text = fmt_num(info.get('dungeons', 0))
    bbox_dun = draw.textbbox((0, 0), dun_text, font=font_mini)
    draw.text((340 - (bbox_dun[2] - bbox_dun[0]), 620), dun_text, font=font_mini, fill=(60,40,30,255))

    draw.text((70, 660), "Caves", font=font_mini, fill=(60,40,30,255))
    caves_text = fmt_num(info.get('caves', 0))
    bbox_caves = draw.textbbox((0, 0), caves_text, font=font_mini)
    draw.text((340 - (bbox_caves[2] - bbox_caves[0]), 690), caves_text, font=font_mini, fill=(60,40,30,255))

    draw.text((70, 730), "Quests", font=font_mini, fill=(60,40,30,255))
    quests_text = fmt_num(info.get('quests', 0))
    bbox_quests = draw.textbbox((0, 0), quests_text, font=font_mini)
    draw.text((340 - (bbox_quests[2] - bbox_quests[0]), 760), quests_text, font=font_mini, fill=(60,40,30,255))

    draw.text((70, 800), "World Events", font=font_mini, fill=(60,40,30,255))
    we_text = fmt_num(info.get('world_events', 0))
    bbox_we = draw.textbbox((0, 0), we_text, font=font_mini)
    draw.text((340 - (bbox_we[2] - bbox_we[0]), 830), we_text, font=font_mini, fill=(60,40,30,255))

    draw.text((370, 520), "PvP", font=font_mini, fill=(60,40,30,255))
    pk_text = fmt_num(info.get('pvp_kill', 0))
    pd_text = fmt_num(info.get('pvp_death', 0))
    pvp_val_text = f"{pk_text} K / {pd_text} D"
    bbox_pvp = draw.textbbox((0, 0), pvp_val_text, font=font_mini)
    draw.text((670 - (bbox_pvp[2] - bbox_pvp[0]), 550), pvp_val_text, font=font_mini, fill=(60,40,30,255))

    draw.text((370, 590), "MobKill", font=font_mini, fill=(60,40,30,255))
    mob_text = fmt_num(info.get('mobs_killed', 0))
    bbox_mob = draw.textbbox((0, 0), mob_text, font=font_mini)
    draw.text((670 - (bbox_mob[2] - bbox_mob[0]), 620), mob_text, font=font_mini, fill=(60,40,30,255))

    draw.text((370, 660), "ChestOpen", font=font_mini, fill=(60,40,30,255))
    chest_text = fmt_num(info.get('chests', 0))
    bbox_chest = draw.textbbox((0, 0), chest_text, font=font_mini)
    draw.text((670 - (bbox_chest[2] - bbox_chest[0]), 690), chest_text, font=font_mini, fill=(60,40,30,255))

    draw.text((370, 730), "WarsDone", font=font_mini, fill=(60,40,30,255))
    wars_done_text = fmt_num(info.get('wars', 0))
    bbox_wars_done = draw.textbbox((0, 0), wars_done_text, font=font_mini)
    draw.text((670 - (bbox_wars_done[2] - bbox_wars_done[0]), 760), wars_done_text, font=font_mini, fill=(60,40,30,255))

    draw.text((370, 800), "WarRank", font=font_mini, fill=(60,40,30,255))
    war_rank_text = f"#{info.get('war_rank_display', 'N/A')}"
    bbox_war_rank = draw.textbbox((0, 0), war_rank_text, font=font_mini)
    draw.text((670 - (bbox_war_rank[2] - bbox_war_rank[0]), 830), war_rank_text, font=font_mini, fill=(60,40,30,255))

    draw.text((690, 520), "First Join:", font=font_mini, fill=(60,40,30,255))
    draw.text((700, 550), f"{info.get('first_join', 'N/A')}", font=font_tiny, fill=(60,40,30,255))

    draw.text((690, 590), "Last Seen:", font=font_mini, fill=(60,40,30,255))
    draw.text((700, 620), f"{info.get('last_join', 'N/A')}", font=font_tiny, fill=(60,40,30,255))

    draw.text((690, 660), "Playtime:", font=font_mini, fill=(60,40,30,255))
    playtime_text = fmt_num(info.get('playtime', 0))
    draw.text((700, 690), playtime_text, font=font_mini, fill=(60,40,30,255))
    bbox = draw.textbbox((700, 690), playtime_text, font=font_mini)
    x_hours = bbox[2] + 5
    draw.text((x_hours, 720), "hours", font=font_prefix, fill=(60,40,30,255))

    draw.text((90, 1070), "Content Clears", font=font_small, fill=(90,60,30,255))

    right_edge_x = 440
    raid_keys = [("NOTG", "notg", 1150), ("NOL", "nol", 1200), ("TCC", "tcc", 1250),
                 ("TNA", "tna", 1300), ("All Raids", "all_raids", 1350)]
    for label, key, y in raid_keys:
        draw.text((100, y), label, font=font_raids, fill=(60,40,30,255))
        num_text = fmt_num(info.get(key, 0))
        bbox = draw.textbbox((0,0), num_text, font=font_raids)
        text_width = bbox[2] - bbox[0]
        x = right_edge_x - text_width
        draw.text((x, y), num_text, font=font_raids, fill=(60,40,30,255))

    wars_text = fmt_num(info.get('wars', 0))
    war_rank_display_text = f"#{info.get('war_rank_display', 'N/A')}"
    world_events_text = fmt_num(info.get('world_events', 0))
    draw.text((475, 1150), "Wars", font=font_raids, fill=(60,40,30,255))
    draw.text((475, 1200), "WEs", font=font_raids, fill=(60,40,30,255))
    y_wars = 1150
    y_world_events = 1200
    x_right_align = 775

    bbox_wars = draw.textbbox((0,0), wars_text, font=font_raids)
    wars_width = bbox_wars[2] - bbox_wars[0]
    draw.text((x_right_align - wars_width, y_wars), wars_text, font=font_raids, fill=(60,40,30,255))

    bbox_war_rank = draw.textbbox((0,0), war_rank_display_text, font=font_mini)
    war_rank_width = bbox_war_rank[2] - bbox_war_rank[0]
    draw.text((x_right_align + 12, y_wars + 12), war_rank_display_text, font=font_mini, fill=(60,40,30,255))

    bbox_we = draw.textbbox((0,0), world_events_text, font=font_raids)
    we_width = bbox_we[2] - bbox_we[0]
    draw.text((x_right_align - we_width, y_world_events), world_events_text, font=font_raids, fill=(60,40,30,255))

    uuid = info.get("uuid", "")
    if uuid and '-' in uuid:
        parts = uuid.split('-')
        if len(parts) == 5:
            line1 = f"{parts[0]}-{parts[1]}"
            line2 = f"{parts[2]}-{parts[3]}-{parts[4]}"
        else:
            line1 = uuid
            line2 = ""
    else:
        line1 = line2 = ""
    draw.text((475, 1275), "UUID", font=font_raids, fill=(90,90,90,255))
    draw.text((600, 1280), line1 + "-", font=font_uuid, fill=(90,90,90,255))
    draw.text((475, 1320), line2, font=font_uuid, fill=(90,90,90,255))

    # --- Top Ranks の描画 ---
    top_ranks = info.get("top_ranks", [])
    if top_ranks:
        rank_base_x = 475
        rank_base_y = 1000  # ← テンプレート画像に合わせて調整してください
        draw.text((rank_base_x, rank_base_y), "Top Ranks", font=font_small, fill=(90, 60, 30, 255))
        
        for i, rank_data in enumerate(top_ranks):
            y_pos = rank_base_y + 45 + (i * 35)
            draw.text((rank_base_x + 10, y_pos), rank_data["category"], font=font_mini, fill=(60, 40, 30, 255))
            
            rank_str = f"#{fmt_num(rank_data['rank'])}"
            bbox = draw.textbbox((0,0), rank_str, font=font_mini)
            draw.text((x_right_align - (bbox[2] - bbox[0]), y_pos), rank_str, font=font_mini, fill=(60, 40, 30, 255))

    draw.text((635, 1400), "Generated by", font=font_mini, fill=(60,40,30,255))
    draw.text((735, 1435), "AtamaWaruiBoi#3244", font=font_mini, fill=(60,40,30,255))

    try:
        img.save(output_path)
    except Exception as e:
        logger.error(f"画像保存失敗: {e}")
    return output_path
