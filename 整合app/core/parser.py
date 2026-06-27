import re

# CJK Unicode ranges — explicit hex (reliable on Windows, unlike [一-鿿])
_CJK = r'[一-鿿㐀-䶿豈-﫿]'


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


_DATE_RE = re.compile(r'^\d{1,2}[/\-]\d{1,2}([/\-]\d{2,4})?$')


def parse_one(text: str) -> dict:
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    out = dict(model='', capacity='', serial='', color='',
               battery='', condition='', warranty='')
    if not lines:
        return out

    # 忽略開頭的日期行（如 06/26）
    if _DATE_RE.match(lines[0]):
        lines = lines[1:]
    if not lines:
        return out

    first = lines[0]
    full  = '\n'.join(lines)
    work  = first  # mutable working copy of first line

    # ── 1. Serial: #英數字 ────────────────────────────────────────────────
    m = re.search(r'#\s*([A-Za-z0-9]+)', work)
    if m:
        out['serial'] = m.group(1)
        work = (work[:m.start()] + work[m.end():]).strip()

    # ── 2. Battery: 電池[容量|健康度]?數字% + strip trailing brackets ──────
    m = re.search(
        r'電池(?:容量|健康度)?\s*[:：]?\s*(\d+)\s*%?'
        r'(?:\s*[（(][^）)]*[）)])?',
        work, re.IGNORECASE)
    if m:
        out['battery'] = m.group(1)
        work = (work[:m.start()] + work[m.end():]).strip()

    # ── 3. Remove any remaining parentheticals (e.g. standalone cycle counts)
    work = re.sub(r'[（(][^）)]*[）)]', '', work).strip()

    # ── 4. Remove box info (not shown on image) ───────────────────────────
    work = re.sub(r'有盒|無盒|原廠盒|全配', '', work)

    # ── 5. Warranty (search full text; clean tokens from work) ────────────
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

    work = re.sub(r'(?:原廠)?保固[\d/\-]*', '', work)
    work = re.sub(r'\d+\s*(?:天|個月|月|年)', '', work)
    work = re.sub(r'原廠', '', work)
    work = re.sub(r'\$[\d,]+', '', work)
    work = re.sub(r'\s+', ' ', work).strip()

    # ── 6. Color: last Chinese cluster remaining in work ──────────────────
    chi = list(re.finditer(_CJK + '+', work))
    if chi:
        last = chi[-1]
        out['color'] = last.group()
        work = (work[:last.start()] + work[last.end():]).strip()

    work = re.sub(r'\s+', ' ', work).strip()

    # ── 7. Remaining = model + capacity title; uppercase ──────────────────
    title = work.upper()

    # ── 8. Extract capacity from title ───────────────────────────────────
    # Handles: 128GB, 8/256GB, 256G→256GB, 256T→256TB
    # Pattern matches X/256GB (RAM/Storage) or plain 128GB
    cap_m = list(re.finditer(r'(\d+(?:/\d+)?)\s*(GB|TB|G\b|T\b)', title, re.IGNORECASE))
    if cap_m:
        last_c = cap_m[-1]
        num  = last_c.group(1)   # e.g. '8/256' or '128'
        unit = last_c.group(2).upper()
        if unit == 'G':
            unit = 'GB'
        elif unit == 'T':
            unit = 'TB'
        out['capacity'] = num + unit                         # '8/256GB' or '128GB'
        out['model']    = title[:last_c.start()].strip()    # everything before capacity
    else:
        # Fallback: lone B suffix (typo for GB), e.g. 256B → 256GB
        cap_b = list(re.finditer(r'(\d+)\s*B\b', title))
        if cap_b:
            last_c = cap_b[-1]
            out['capacity'] = last_c.group(1) + 'GB'
            out['model']    = re.sub(r'\s*\d+\s*B\b', '', title).strip()
        else:
            out['model'] = title

    if not out['warranty']:
        out['warranty'] = _auto_warranty(out['model'])

    # ── 9. Condition ──────────────────────────────────────────────────────
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
