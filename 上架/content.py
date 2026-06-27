"""商品內容生成模組"""

import re
from datetime import date
from pathlib import Path


def accessories(model: str) -> str | None:
    """根據機型決定配件文字，回傳 None 表示不顯示配件那行。"""
    upper = model.upper()

    if 'SONY' in upper:
        return None

    m = re.search(r'IPHONE\s*(\d+)', upper)
    if m:
        number = int(m.group(1))
        if number <= 11:
            return '傳輸線、旅充頭'
        else:
            return '傳輸線'

    if 'APPLE WATCH' in upper:
        return '傳輸線'

    if 'SAMSUNG' in upper:
        return '傳輸線'

    return '傳輸線、旅充頭'


def product_name(data: dict) -> str:
    """商品名稱格式：{model} {capacity} #{serial}"""
    return f"{data['model']} {data['capacity']} #{data['serial']}"


def product_slug(sequence: int) -> str:
    """商品網址格式：{YYYYMMDD}-{sequence}"""
    today = date.today().strftime('%Y%m%d')
    return f"{today}-{sequence}"


def _warranty_display(warranty: str) -> str:
    """內部函式：格式化保固顯示文字。"""
    if warranty.startswith('保固'):
        return warranty[2:]
    return warranty


def brief_description(data: dict) -> str:
    """商品簡述純文字。"""
    acc = accessories(data['model'])
    warranty_text = _warranty_display(data['warranty'])

    lines = [
        '【重點資訊】【!!下單前請先詢問!!】',
        f"序號：#{data['serial']}",
    ]
    if acc is not None:
        lines.append(f'配件：{acc}')
    lines += [
        f"電池健康度：{data['battery']}%",
        f"機況：{data['condition']}",
        f'原廠保固：{warranty_text}',
        '',
        '【全館免運費實施中！】',
        '續航無憂（電池專業檢測，保證續航正常）',
        '在地店面（台中實體據點，售後服務跑不掉）',
        '機況透明（100% 實機實拍，所見即所得！）',
    ]
    return '\n'.join(lines)


def full_description_html(data: dict) -> str:
    """商品介紹完整 HTML。"""
    acc = accessories(data['model'])
    warranty_text = _warranty_display(data['warranty'])

    fixed_template = (Path(__file__).parent / 'template_fixed.html').read_text(encoding='utf-8')

    acc_line = ''
    if acc is not None:
        acc_line = f'\n\t<li class="product-description"><strong>配件</strong>：{acc}</li>'

    html = (
        '<div class="product-description"><strong>【重點資訊】【!!下單前請先詢問!!】</strong>\n'
        '<ul>\n'
        f'\t<li class="product-description"><strong>型號</strong>：二手 {data["model"]} {data["capacity"]}&nbsp;{data["color"]}&nbsp;</li>\n'
        f'\t<li class="product-description"><strong>序號</strong>：#{data["serial"]}&nbsp;</li>'
        f'{acc_line}\n'
        f'\t<li class="product-description"><strong>電池健康度</strong>：{data["battery"]}%</li>\n'
        f'\t<li class="product-description"><strong>機況</strong>：{data["condition"]}</li>\n'
        f'\t<li class="product-description"><strong>原廠保固</strong>：{warranty_text}</li>\n'
        '</ul>\n'
        f'{fixed_template}'
    )
    return html
