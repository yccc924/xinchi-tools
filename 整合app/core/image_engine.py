from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

BLACK = (  0,   0,   0)
WHITE = (255, 255, 255)
DARK  = ( 25,  25,  25)

_BASE          = Path(__file__).parent
FONT_INFO_PATH = _BASE / 'assets' / '王漢宗顏楷體繁.ttf'
FONT_BAR_PATH  = _BASE / 'assets' / 'Garet-Heavy.otf'
TEMPLATE_PATH  = _BASE / 'assets' / '二手機範本.jpg'

INFO_H   = 173
MAIN_TOP = 179
BAR_TOP  = 917
BAR_BOT  = 1019
LOGO_W   = 288


def _font(size: int) -> ImageFont.FreeTypeFont:
    for p in (FONT_INFO_PATH, _BASE / 'assets' / 'font.ttf'):
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
    warranty:   str,
    battery:    str,
    color:      str,
    serial:     str,
    model:      str,
    capacity:   str,
    condition:  str,
    output_path: Path,
) -> Path:
    template = Image.open(TEMPLATE_PATH).convert('RGB')
    W, H = template.size

    main_h = BAR_TOP - MAIN_TOP

    phone  = Image.open(image_path).convert('RGB')
    ph_w, ph_h = phone.size
    scale  = max(W / ph_w, main_h / ph_h)
    new_w  = int(ph_w * scale)
    new_h  = int(ph_h * scale)
    scaled = phone.resize((new_w, new_h), Image.LANCZOS)

    x_off = (new_w - W)      // 2
    y_off = (new_h - main_h) // 2
    crop  = scaled.crop((x_off, y_off, x_off + W, y_off + main_h))

    result = template.copy()
    result.paste(crop, (0, MAIN_TOP))
    draw = ImageDraw.Draw(result)

    f_info = _font(int(H * 0.065))

    text_left_x = LOGO_W + 22
    right_edge  = W - 20
    y1 = int(INFO_H * 0.26)
    y2 = int(INFO_H * 0.76)

    warranty_label = warranty if warranty.startswith('保固') else f'店保{warranty}'

    left_max_w  = int(W * 0.40)
    right_max_w = 290

    def _fit(text: str, max_w: int = left_max_w) -> ImageFont.FreeTypeFont:
        for s in range(int(H * 0.065), 20, -2):
            f = _font(s)
            if draw.textbbox((0, 0), text, font=f, anchor='lt')[2] <= max_w:
                return f
        return _font(20)

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
        f_left = _fit_pair(warranty_label, f'電池{battery}%')
        _text((text_left_x, y1), warranty_label,    f_left, 'lm')
        _text((text_left_x, y2), f'電池{battery}%', f_left, 'lm')
    else:
        y_mid = (y1 + y2) // 2
        f_left = _fit(warranty_label)
        _text((text_left_x, y_mid), warranty_label, f_left, 'lm')

    _text((right_edge, y1), color,         _fit(color,          right_max_w), 'rm')
    _text((right_edge, y2), f'#{serial}',  _fit(f'#{serial}',   right_max_w), 'rm')

    bar_center_y = (BAR_TOP + BAR_BOT) // 2
    model_text   = f'{model.upper()} {capacity.upper()}'
    max_text_w   = 897

    f_model = _font_bar(70)
    for fsize in range(70, 8, -2):
        f_model = _font_bar(fsize)
        bbox = draw.textbbox((0, 0), model_text, font=f_model, anchor='lt')
        if (bbox[2] - bbox[0]) <= max_text_w:
            break

    draw.text((W // 2, bar_center_y), model_text,
              font=f_model, fill=WHITE, anchor='mm')

    jpg_path = output_path.with_suffix('.jpg')
    jpg_path.parent.mkdir(parents=True, exist_ok=True)
    result.save(jpg_path, quality=95)
    return jpg_path
