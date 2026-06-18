from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# 顏色
BLACK = (  0,   0,   0)
WHITE = (255, 255, 255)
DARK  = ( 25,  25,  25)   # info strip 文字（深色背景為白底）

_BASE          = Path(__file__).parent
FONT_INFO_PATH = _BASE / "assets" / "王漢宗顏楷體繁.ttf"
FONT_BAR_PATH  = _BASE / "assets" / "Garet-Heavy.otf"
TEMPLATE_PATH  = _BASE / "二手機範本.jpg"

# 從像素分析得出的範本精確座標（1080×1080）
INFO_H   = 173   # info strip 結束 y（橘線上緣）
MAIN_TOP = 179   # 手機照片區域起始 y（橘線下緣）
BAR_TOP  = 917   # 底部深色條起始 y
BAR_BOT  = 1019  # 底部深色條結束 y
LOGO_W   = 288   # logo 方塊右緣 x


def _font(size: int) -> ImageFont.FreeTypeFont:
    for p in (FONT_INFO_PATH, _BASE / "assets" / "font.ttf"):
        try:
            return ImageFont.truetype(str(p), size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _font_bar(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(FONT_BAR_PATH), size)
    except OSError:
        return _font(size)


def render(
    image_path: Path,
    warranty:  str,
    battery:   str,
    color:     str,
    serial:    str,
    model:     str,
    capacity:  str,
    condition: str,        # 保留欄位，目前不顯示在圖上
    output_path: Path,
) -> Path:
    # ── 1. 載入範本 ────────────────────────────────────────────────
    template = Image.open(TEMPLATE_PATH).convert("RGB")
    W, H = template.size   # 1080×1080

    main_h = BAR_TOP - MAIN_TOP  # 738px

    # ── 2. 載入手機照片，縮放裁切至主區域 ─────────────────────────
    phone = Image.open(image_path).convert("RGB")
    ph_w, ph_h = phone.size
    scale  = max(W / ph_w, main_h / ph_h)
    new_w  = int(ph_w * scale)
    new_h  = int(ph_h * scale)
    scaled = phone.resize((new_w, new_h), Image.LANCZOS)

    x_off = (new_w - W)      // 2
    y_off = (new_h - main_h) // 2
    crop  = scaled.crop((x_off, y_off, x_off + W, y_off + main_h))

    # ── 3. 合成：手機照片貼入範本主區域 ───────────────────────────
    result = template.copy()
    result.paste(crop, (0, MAIN_TOP))
    draw = ImageDraw.Draw(result)

    # ── 4. Info strip 文字（深色，白底背景）────────────────────────
    f_info = _font(int(H * 0.065))   # ≈70px

    text_left_x = LOGO_W + 22             # ≈310  保固/電池左緣（logo 右側）
    right_edge  = W - 20                  # ≈1060 顏色/序號右緣
    y1 = int(INFO_H * 0.26)              # ≈45  上行
    y2 = int(INFO_H * 0.76)              # ≈132 下行

    warranty_label = warranty if warranty.startswith('保固') else f'店保{warranty}'

    left_max_w  = int(W * 0.40)           # ≈432px（左欄可用寬度）
    right_max_w = 290

    def _fit(text: str, max_w: int = left_max_w) -> ImageFont.FreeTypeFont:
        for s in range(int(H * 0.065), 20, -2):
            f = _font(s)
            if draw.textbbox((0, 0), text, font=f, anchor='lt')[2] <= max_w:
                return f
        return _font(20)

    # 保固和電池共用同一字體大小（取兩者都能放下的最大 size）
    def _fit_pair(t1: str, t2: str) -> ImageFont.FreeTypeFont:
        for s in range(int(H * 0.065), 20, -2):
            f = _font(s)
            bb = lambda t: draw.textbbox((0, 0), t, font=f, anchor='lt')[2]
            if bb(t1) <= left_max_w and bb(t2) <= left_max_w:
                return f
        return _font(20)

    SHADOW = BLACK
    SH = 2

    def _text(xy, text, font, anchor):
        draw.text((xy[0] + SH, xy[1] + SH), text, font=font, fill=SHADOW, anchor=anchor)
        draw.text(xy,                         text, font=font, fill=DARK,   anchor=anchor)

    if battery:
        f_left = _fit_pair(warranty_label, f"電池{battery}%")
        _text((text_left_x, y1), warranty_label,    f_left, "lm")
        _text((text_left_x, y2), f"電池{battery}%", f_left, "lm")
    else:
        y_mid = (y1 + y2) // 2
        f_left = _fit(warranty_label)
        _text((text_left_x, y_mid), warranty_label, f_left, "lm")
    _text((right_edge,  y1), color,              _fit(color,      right_max_w),   "rm")
    _text((right_edge,  y2), f"#{serial}",       _fit(f"#{serial}", right_max_w), "rm")

    # ── 5. 底部黑條文字（白色，自動縮小確保不超出圖面寬度）──────────
    bar_center_y = (BAR_TOP + BAR_BOT) // 2  # ≈968
    model_text   = f"{model.upper()} {capacity.upper()}"
    max_text_w   = 897   # 深色 bar 內側寬 927px，左右各留 15px 邊距

    f_model = _font_bar(70)
    for fsize in range(70, 8, -2):
        f_model = _font_bar(fsize)
        bbox = draw.textbbox((0, 0), model_text, font=f_model, anchor="lt")
        if (bbox[2] - bbox[0]) <= max_text_w:
            break

    draw.text((W // 2, bar_center_y), model_text,
              font=f_model, fill=WHITE, anchor="mm")

    # ── 6. 輸出 JPG（無論輸入格式都統一輸出 jpg）──────────────────
    jpg_path = output_path.with_suffix(".jpg")
    jpg_path.parent.mkdir(parents=True, exist_ok=True)
    result.save(jpg_path, quality=95)
    print(f"  ✓ 已儲存：{jpg_path.name}")
    return jpg_path
