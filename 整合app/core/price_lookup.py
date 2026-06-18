import re
import openpyxl


def normalize_model(raw: str) -> str:
    return str(raw).strip().upper().replace(' ', '').replace('／', '/')


def load_excel(path: str) -> tuple[dict, set]:
    """Returns (price_db, warranty_keys)"""
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    db: dict = {}
    warranty_keys: set = set()

    i = 0
    while i < len(rows):
        model_raw = rows[i][0]
        if model_raw is None or str(model_raw).strip() in ('', 'nan'):
            i += 1
            continue
        if any(kw in str(model_raw) for kw in ('二手機', '賣價', '開價')):
            i += 1
            continue
        if i + 1 >= len(rows):
            break

        header_row = rows[i]
        price_row  = rows[i + 1]
        model_key  = normalize_model(model_raw)

        for col in range(1, len(header_row)):
            spec  = header_row[col]
            price = price_row[col] if col < len(price_row) else None
            if spec is None or price is None:
                continue
            spec_s = str(spec).strip()
            if not spec_s or spec_s == 'nan':
                continue

            cap_m = re.search(r'(\d+)(G|T)', spec_s, re.IGNORECASE)
            if not cap_m:
                continue
            capacity = cap_m.group(1) + cap_m.group(2).upper()

            if '80~89' in spec_s or '80-89' in spec_s or '沒有100%' in spec_s:
                btype = '80~89'
            else:
                btype = '90~100'

            key = (model_key, capacity, btype)
            parts = str(price).strip().split()
            try:
                db[key] = int(float(parts[0]))
            except Exception:
                db[key] = str(price)
                print(f"[price_lookup] 警告：key={key} 的價格欄位無法解析為整數，原始值={price!r}")

            if '保內100%' in spec_s and len(parts) >= 2:
                try:
                    db[(model_key, capacity, '保內100%')] = int(float(parts[1]))
                except Exception:
                    pass

            if '保內' in spec_s and len(parts) < 2:
                warranty_keys.add(key)

        i += 2

    return db, warranty_keys


def detect_model(header: str, price_db: dict) -> str:
    header_upper = header.upper().replace(' ', '')
    m = re.search(r'IPHONE\s+(.*?)\s*\d+\s*[GT]', header, re.IGNORECASE)
    model_text = m.group(1).upper().replace(' ', '') if m else header_upper

    known = sorted(set(k[0] for k in price_db), key=len, reverse=True)
    for model_key in known:
        if '/' in model_key:
            for part in sorted(model_key.split('/'), key=len, reverse=True):
                if len(part) > 2 and (part in model_text or part in header_upper):
                    return model_key
        else:
            if (model_key == model_text
                    or (model_key in model_text and len(model_key) > 2)
                    or (model_key in header_upper and len(model_key) > 2)):
                return model_key
    return '未知'


def lookup_price(price_db: dict, warranty_keys: set,
                 model: str, capacity: str, battery: str,
                 raw_block: str) -> int | None:
    if not model or not capacity or model == '未知':
        return None

    try:
        batt_val = int(battery) if battery else 100
    except ValueError:
        batt_val = 100

    btype = '80~89' if batt_val < 90 else '90~100'
    price = price_db.get((model, capacity, btype))
    if price is None and btype == '80~89':
        price = price_db.get((model, capacity, '90~100'))

    has_bonus = (
        ('原廠保固' in raw_block and '無原廠保固' not in raw_block)
        or '換過原廠電池' in raw_block
    )
    if batt_val == 100 and has_bonus:
        wp = price_db.get((model, capacity, '保內100%'))
        if isinstance(wp, int):
            price = wp
        elif (model, capacity, btype) not in warranty_keys and isinstance(price, int):
            price = price + 1000

    return price if isinstance(price, int) else None
