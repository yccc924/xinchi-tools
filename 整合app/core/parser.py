import re

_COLORS = [
    '深空黑', '黑色鈦金屬', '白色鈦金屬', '原色鈦金屬', '自然鈦金屬',
    '星光色', '午夜色', '黑色', '白色', '藍色', '紅色', '綠色',
    '紫色', '金色', '銀色', '灰色', '粉色', '黃色',
]


def _auto_warranty(model: str) -> str:
    m = model.upper()
    if 'IPHONE' not in m:
        return '30天'
    if re.search(r'\bX[SR]?\b', m):
        return '30天'
    if re.search(r'\bSE\b', m):
        return '30天'
    if re.search(r'\bAIR\b', m):
        return '90天'
    num = re.search(r'IPHONE\s*(\d+)', m)
    if num and int(num.group(1)) >= 12:
        return '90天'
    return '30天'


def parse_one(text: str) -> dict:
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    out = dict(model='', capacity='', serial='', color='',
               battery='', condition='', warranty='')
    if not lines:
        return out

    first = lines[0]
    full  = '\n'.join(lines)

    m = re.search(r'電池[健康度]*\s*[:：]?\s*(\d+)\s*%?', first, re.IGNORECASE)
    if m:
        out['battery'] = m.group(1)
    m = re.search(r'#\s*(\w+)', first)
    if m:
        out['serial'] = m.group(1)
    m = re.search(r'(\d+\s*[GT]B)', first, re.IGNORECASE)
    if m:
        out['capacity'] = m.group(1).upper().replace(' ', '')
    for c in _COLORS:
        if c in first:
            out['color'] = c
            break

    m = re.search(r'保固\s*(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})', full)
    if m:
        out['warranty'] = f"保固{m.group(1)}{int(m.group(2)):02d}{int(m.group(3)):02d}"
    else:
        m = re.search(r'保固\s*(\d{6,})', full)
        if m:
            out['warranty'] = '保固' + m.group(1)
        else:
            m = re.search(r'(\d+\s*(?:天|個月|月|年))', first)
            if m:
                out['warranty'] = m.group(1)

    clean = first
    for pat in [r'電池[健康度]*\s*[:：]?\s*\d+\s*%?(?:\s*[（(]\d+[）)])?',
                r'#\s*\w+', r'\d+\s*[GT]B', r'\$[\d,]+',
                r'有盒|無盒|原廠盒|全配', r'(?:原廠)?保固[\d/\-]*',
                r'\d+\s*(?:天|個月|月|年)', r'原廠', r'\b0\b']:
        clean = re.sub(pat, '', clean, flags=re.IGNORECASE)
    if out['color']:
        clean = clean.replace(out['color'], '')
    try:
        clean = re.sub(r'[一-鿿㐀-䶿＀-￯]+', '', clean)
    except re.error as _e:
        print(f"[parser] 警告：Unicode 中文字元正規式失敗（{_e}），跳過此過濾步驟，保留原文")

    clean = re.sub(r'[^\w\s]', ' ', clean)
    clean = re.sub(r'\b\d{3,}\b', '', clean)
    out['model'] = ' '.join(clean.split())

    if not out['warranty']:
        out['warranty'] = _auto_warranty(out['model'])

    parts = []
    box = re.search(r'(有盒|無盒|原廠盒|全配)', first)
    if box:
        parts.append(box.group(1))
    for line in lines[1:]:
        if not re.match(r'^\$[\d,]+$', line):
            parts.append(line)
    out['condition'] = '  '.join(parts)
    return out


def parse_all(raw: str) -> list[dict]:
    blocks = re.split(r'\n{2,}', raw.strip())
    return [parse_one(b) for b in blocks if b.strip()]
