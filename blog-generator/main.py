import os
import re
import time
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import feedparser
import requests
from bs4 import BeautifulSoup
from openai import OpenAI

from urllib.parse import urlparse

from config import (
    NVIDIA_API_KEY, NVIDIA_BASE_URL, NVIDIA_MODEL,
    GEMINI_API_KEY, GEMINI_MODEL, PROVIDER,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    RSS_FEEDS, WEBSITE_SOURCES, DONE_FILE, PROMPT_FILE, TONE_SAMPLES_FILE,
    OUTPUT_DIR, API_DELAY, TELEGRAM_RETRY_DELAY, MAX_PER_RUN,
)

TW_TZ = timezone(timedelta(hours=8))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── 工具函式 ──────────────────────────────────────────────────────────────────

def get_today_taiwan():
    return datetime.now(TW_TZ).date()


def load_done_urls() -> set:
    if not os.path.exists(DONE_FILE):
        return set()
    with open(DONE_FILE, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def save_done_urls(new_urls: list):
    existing = load_done_urls()
    all_urls = existing | set(new_urls)
    with open(DONE_FILE, "w", encoding="utf-8") as f:
        for url in sorted(all_urls):
            f.write(url + "\n")


def load_text(path: str) -> str:
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def save_text(path: str, content: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# ── 優惠/折扣文章過濾 ──────────────────────────────────────────────────────────

_DEAL_KEYWORDS = [
    'deal', 'deals', 'discount', 'discounts', 'coupon', 'coupons',
    'sale', 'on sale', 'clearance', 'promo', 'promotion',
    'save ', 'saving', 'savings', '% off', 'price drop', 'price cut',
    'amazon', 'best buy', 'walmart', 'target', 'costco',
    'prime day', 'prime sale', 'flash sale', 'black friday', 'cyber monday',
    'limited time', 'expires', 'voucher',
    'dirt-cheap', 'dirt cheap', 'grab this', 'snag', 'scored a',
    'for just $', 'for only $', 'only $', 'for a steal', 'steal at',
    'anker', 'belkin', 'aukey',   # 第三方配件品牌，通常是促銷文
]

_DEAL_URL_SEGMENTS = ['/deals/', '/deal/', '/coupon/', '/discount/', '/sale/']


def is_deal_article(title: str, url: str) -> bool:
    """第三方優惠、折扣、Amazon 特賣類文章回傳 True，應排除。"""
    t = title.lower()
    u = url.lower()
    if any(kw in t for kw in _DEAL_KEYWORDS):
        return True
    if any(seg in u for seg in _DEAL_URL_SEGMENTS):
        return True
    return False


# ── RSS ────────────────────────────────────────────────────────────────────────

def fetch_rss_articles() -> list[dict]:
    today = get_today_taiwan()
    articles = []

    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            source_name = getattr(feed.feed, "title", feed_url)

            for entry in feed.entries:
                pub_date = None
                for attr in ("published_parsed", "updated_parsed"):
                    parsed = getattr(entry, attr, None)
                    if parsed:
                        pub_date = datetime(*parsed[:6], tzinfo=timezone.utc).astimezone(TW_TZ).date()
                        break

                if pub_date == today:
                    articles.append({
                        "url": entry.link,
                        "title": entry.title,
                        "summary": getattr(entry, "summary", ""),
                        "source": source_name,
                    })

            logger.info(f"RSS {source_name}：找到 {sum(1 for a in articles if a['source'] == source_name)} 篇今日文章")
        except Exception as e:
            logger.error(f"RSS 擷取失敗 {feed_url}：{e}")

    return articles


# ── 全文擷取 ───────────────────────────────────────────────────────────────────

CONTENT_SELECTORS = [
    "article",
    '[class*="article-body"]',
    '[class*="post-content"]',
    '[class*="entry-content"]',
    '[class*="article-content"]',
    "main",
]

# 只跟進這些科技媒體的引用連結
_TRUSTED_DOMAINS = {
    "9to5mac.com", "macrumors.com", "macworld.com", "appleinsider.com",
    "theverge.com", "arstechnica.com", "bloomberg.com", "reuters.com",
    "techcrunch.com", "engadget.com", "wired.com", "cnet.com",
}


def _extract_text(soup: BeautifulSoup) -> str | None:
    for selector in CONTENT_SELECTORS:
        node = soup.select_one(selector)
        if node:
            text = node.get_text(separator="\n", strip=True)
            if len(text) > 200:
                return text
    return soup.body.get_text(separator="\n", strip=True) if soup.body else None


def fetch_full_content(url: str) -> str | None:
    """抓主文，並跟進文章內引用的可信科技媒體連結（最多 2 篇）補充內容。"""
    headers = {"User-Agent": "Mozilla/5.0 (compatible; BlogBot/1.0)"}

    try:
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "lxml")

        # 收集引用連結（在移除 nav/footer 前先抓）
        main_domain = urlparse(url).netloc.replace("www.", "")
        cited_urls = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.startswith("http"):
                continue
            domain = urlparse(href).netloc.replace("www.", "")
            if domain in _TRUSTED_DOMAINS and domain != main_domain and href != url:
                if href not in cited_urls:
                    cited_urls.append(href)
            if len(cited_urls) >= 2:
                break

        # 清理並抓主文
        for tag in soup.find_all(["script", "style", "nav", "footer", "aside", "iframe", "noscript"]):
            tag.decompose()
        main_text = _extract_text(soup)
        if not main_text:
            return None

        parts = [main_text]

        # 抓引用文章補充內容
        for cited_url in cited_urls:
            try:
                r = requests.get(cited_url, headers=headers, timeout=15)
                r.raise_for_status()
                s = BeautifulSoup(r.content, "lxml")
                for tag in s.find_all(["script", "style", "nav", "footer", "aside", "iframe", "noscript"]):
                    tag.decompose()
                extra = _extract_text(s)
                if extra and len(extra) > 200:
                    parts.append(f"\n---（引用來源：{cited_url}）---\n{extra}")
                    logger.info(f"補充引用文章：{cited_url}")
            except Exception as e:
                logger.warning(f"引用文章抓取失敗 {cited_url}：{e}")

        return "\n\n".join(parts)

    except Exception as e:
        logger.warning(f"全文擷取失敗 {url}：{e}")
        return None


# ── 直接爬網站 ────────────────────────────────────────────────────────────────

def fetch_articles_from_websites() -> list[dict]:
    articles = []
    for source in WEBSITE_SOURCES:
        try:
            headers = {"User-Agent": "Mozilla/5.0 (compatible; BlogBot/1.0)"}
            resp = requests.get(source["url"], headers=headers, timeout=20)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.content, "lxml")
            parsed_base = urlparse(source["url"])
            seen_urls: set = set()
            found = []

            for article_tag in soup.find_all("article"):
                heading = article_tag.find(["h2", "h3", "h1"])
                if not heading:
                    continue
                title = heading.get_text(strip=True)
                if len(title) < 10:
                    continue

                a = heading.find("a", href=True) or article_tag.find("a", href=True)
                if not a:
                    continue
                href = a["href"]
                if href.startswith("/"):
                    href = f"{parsed_base.scheme}://{parsed_base.netloc}{href}"
                if not href.startswith("http"):
                    continue
                if href in seen_urls:
                    continue
                seen_urls.add(href)
                found.append({"url": href, "title": title, "summary": "", "source": source["name"]})

            articles.extend(found)
            logger.info(f"網站 {source['name']}：找到 {len(found)} 篇文章")
        except Exception as e:
            logger.error(f"網站爬取失敗 {source['url']}：{e}")

    return articles


# ── NVIDIA API ─────────────────────────────────────────────────────────────────

def generate_prompt_from_tone(client: OpenAI, tone_samples: str) -> str:
    logger.info("從 tone_samples.txt 分析語氣，生成寫作指南...")

    resp = client.chat.completions.create(
        model=NVIDIA_MODEL,
        messages=[
            {
                "role": "system",
                "content": "你是一位專業的內容策略師，擅長分析寫作風格並制定寫作指南。請用繁體中文回答。",
            },
            {
                "role": "user",
                "content": (
                    "以下是語氣範本文章，請仔細分析寫作風格、語氣特徵、用詞習慣，"
                    "並輸出一份完整的 Markdown 格式寫作指南，供後續每篇文章改寫時參考。\n\n"
                    "指南必須包含：\n"
                    "1. 整體語氣風格定義\n"
                    "2. 慣用詞彙與台灣用語示例\n"
                    "3. 句子結構與段落節奏\n"
                    "4. 如何自然使用「小編」自稱\n"
                    "5. 開頭引言寫法（含示例）\n"
                    "6. 數字小標題格式（1. 2. 3.）\n"
                    "7. 每段小結的寫法\n"
                    "8. 結尾總結 + CTA 寫法\n"
                    "9. 規格表格呈現方式\n"
                    "10. 禁止事項\n\n"
                    f"語氣範本：\n{tone_samples}"
                ),
            },
        ],
        max_tokens=2500,
        temperature=0.6,
    )
    return resp.choices[0].message.content


def rank_articles_by_traffic(client: OpenAI, articles: list[dict], top_n: int) -> list[dict]:
    if len(articles) <= top_n:
        return articles

    logger.info(f"從 {len(articles)} 篇中用 AI 選出前 {top_n} 篇高流量文章...")
    titles_text = "\n".join(f"{i+1}. [{a['source']}] {a['title']}" for i, a in enumerate(articles))

    resp = client.chat.completions.create(
        model=NVIDIA_MODEL,
        messages=[
            {
                "role": "system",
                "content": "你是科技媒體編輯，擅長判斷哪些科技新聞標題最能吸引台灣讀者點擊。",
            },
            {
                "role": "user",
                "content": (
                    f"以下是科技網站文章清單，請先排除所有屬於「第三方優惠/折扣/促銷/特賣/配件特價」的文章，"
                    f"再從剩餘文章中選出最可能帶來高流量的前 {top_n} 篇。\n\n"
                    "【排除標準】只要符合以下任一條件就排除：\n"
                    "- 文章主題是特定零售商（Amazon、Best Buy、Walmart 等）的特賣或折扣\n"
                    "- 標題有價格優惠意味（cheap、dirt-cheap、price cut、grab this、snag、for $XX、% off 等）\n"
                    "- 文章是第三方配件品牌（Anker、Belkin 等）的促銷推薦\n"
                    "- 任何「Prime Day / Black Friday / 限時特賣」相關內容\n\n"
                    "【選文標準】話題熱度、Apple 產品重要性、台灣讀者興趣、標題吸引力。\n\n"
                    f"只回傳 {top_n} 個編號，用逗號分隔，例如：3,7,12,1,5\n"
                    f"若排除後剩餘不足 {top_n} 篇，只回傳實際可用的編號。\n\n"
                    f"{titles_text}"
                ),
            },
        ],
        max_tokens=50,
        temperature=0.3,
    )

    raw = resp.choices[0].message.content.strip()
    indices = []
    for part in re.split(r"[,\s]+", raw):
        part = part.strip().strip(".")
        if part.isdigit():
            idx = int(part) - 1
            if 0 <= idx < len(articles) and idx not in indices:
                indices.append(idx)

    selected = [articles[i] for i in indices[:top_n]]
    return selected


def rewrite_article(client: OpenAI, title: str, content: str, guidelines: str,
                    css: str = '', tone_samples: str = '') -> str:
    """回傳包含四個自訂 tag 的原始字串，由呼叫方解析。"""
    tone_section = f"""
---
# 語氣範本（直接模仿以下文章的語氣、用詞與節奏）
{tone_samples}
---
""" if tone_samples.strip() else ''

    system_msg = f"""{guidelines}{tone_section}"""

    user_msg = f"""請將以下文章改寫成繁體中文部落格文章。

原文標題：{title}

原文內容：
{content}

---

輸出格式：嚴格按照以下四個 tag，不要輸出任何其他文字。

<title>台灣科技部落格風格標題（18–32 字，含產品名稱、數字、情緒動詞）</title>
<desc>SEO 描述，最多 150 字</desc>
<kw>5 個繁體中文關鍵字，半型逗號分隔</kw>
<content>
開頭引言（必須）：
<p>1–2 句背景 + 核心亮點 + 一句讓讀者想繼續看的話。熱情活潑語氣，可加小編感受。</p>

主體章節（每個章節結構如下，至少 2 個）：
<h3 class="highlight-title">1. 大標題</h3>
<p>內文（3–5 句，每個章節說不同的事，不重複其他章節）</p>
（若此章節有細項才加 h4，否則省略）
<h4 class="section-title">小標題（可選）</h4>
<p>細項內文</p>

<h3 class="highlight-title">2. 大標題</h3>
<p>內文</p>
<table class="spec-table">（有規格數據時才加）</table>

總結（必須）：
<h3 class="highlight-title">總結與購買建議</h3>
<p>整體評價（1–2 句）</p>
<ul>
  <li><strong>適合族群 A：</strong>建議...</li>
  <li><strong>二手市場觀點：</strong>這個消息對舊機殘值的影響...</li>
</ul>
<p>小編幽默收尾（1 句，可以有哈哈哈）</p>

注意：
- <content> 只輸出上述 HTML 片段，不含外層 <div class="article-content">
- 大標題一律用 <h3 class="highlight-title">，小標題（有細項時）才用 <h4 class="section-title">
- 不使用 h1、h2
- <strong class="text-highlight"> 用於產品名稱、數字、重要規格（橘色）
- 有規格比較時用 <table class="spec-table">
- 禁止使用簡體字或中國用語（芯片→晶片、内存→記憶體、信息→訊息等）
</content>"""

    if PROVIDER == "gemini":
        return _rewrite_with_gemini(system_msg, user_msg)
    else:
        return _rewrite_with_nvidia(client, system_msg, user_msg)


def _rewrite_with_gemini(system_msg: str, user_msg: str) -> str:
    from google import genai
    from google.genai import types

    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    response = gemini_client.models.generate_content(
        model=GEMINI_MODEL,
        contents=user_msg,
        config=types.GenerateContentConfig(
            system_instruction=system_msg,
            temperature=0.72,
            max_output_tokens=8192,
        ),
    )
    return response.text.strip()


def _rewrite_with_nvidia(client: OpenAI, system_msg: str, user_msg: str) -> str:
    resp = client.chat.completions.create(
        model=NVIDIA_MODEL,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        max_tokens=8192,
        temperature=0.72,
    )
    return resp.choices[0].message.content.strip()


# ── HTML 產生 ──────────────────────────────────────────────────────────────────

_CTA_BLOCK = """\
<hr />
<p>👉 加入官方 LINE，讓我幫你精準找出最值得的一台。<a href="https://lin.ee/9LzFhZu" target="_blank" rel="noopener">點我加入</a></p>
<p>👉 加入我們的 LINE 社群！每天上架馬上報給你知道。<a href="https://line.me/ti/g2/2ofv-ff5V1O6ol0HEWM7USM7BILMry17XjTplg?utm_source=invitation&utm_medium=link_copy&utm_campaign=default" target="_blank" rel="noopener">點我加入社群</a></p>"""


def build_html(title: str, content: str, source: str, url: str, date_str: str,
               css: str = "", desc: str = "", kw: str = "") -> str:
    # css 已含 <style>...</style> 標籤，直接放入 <head> 即可，勿再包一層
    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="{desc}">
    <meta name="keywords" content="{kw}">
    <title>{title}</title>
    {css}
</head>
<body>
    <div class="page-wrapper">
        <header class="post-header">
            <h1 class="post-title">{title}</h1>
            <div class="post-meta">
                <span>來源：<a href="{url}" target="_blank" rel="noopener">{source}</a></span>
                <span>{date_str}</span>
            </div>
        </header>
        <div class="article-content">
            {content}
            {_CTA_BLOCK}
        </div>
        <footer class="post-footer">
            <p>原文連結：<a href="{url}" target="_blank" rel="noopener">{url}</a></p>
        </footer>
    </div>
</body>
</html>"""


def safe_filename(title: str, date_str: str) -> str:
    slug = re.sub(r"[^\w\-]", "_", title[:60]).strip("_")
    return f"{date_str}_{slug}.html"


# ── Telegram ───────────────────────────────────────────────────────────────────

def _tg_post(endpoint: str, **kwargs) -> bool:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{endpoint}"
    try:
        resp = requests.post(url, timeout=30, **kwargs)
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Telegram {endpoint} 失敗：{e}")
        return False


def tg_send_message(text: str, retry: bool = True) -> bool:
    ok = _tg_post("sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"})
    if not ok and retry:
        logger.info(f"等待 {TELEGRAM_RETRY_DELAY} 秒後重試...")
        time.sleep(TELEGRAM_RETRY_DELAY)
        return tg_send_message(text, retry=False)
    return ok


def tg_send_file(filepath: str, caption: str = "", retry: bool = True) -> bool:
    with open(filepath, "rb") as f:
        ok = _tg_post("sendDocument", files={"document": f}, data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption})
    if not ok and retry:
        logger.info(f"等待 {TELEGRAM_RETRY_DELAY} 秒後重試...")
        time.sleep(TELEGRAM_RETRY_DELAY)
        return tg_send_file(filepath, caption, retry=False)
    return ok


# ── 主程式 ─────────────────────────────────────────────────────────────────────

def main():
    Path(OUTPUT_DIR).mkdir(exist_ok=True)

    client = OpenAI(api_key=NVIDIA_API_KEY, base_url=NVIDIA_BASE_URL)

    # 確保 prompt.md 有內容
    guidelines = load_text(PROMPT_FILE)
    if not guidelines:
        tone_samples = load_text(TONE_SAMPLES_FILE)
        if tone_samples:
            guidelines = generate_prompt_from_tone(client, tone_samples)
            save_text(PROMPT_FILE, guidelines)
            logger.info("prompt.md 已生成")
            time.sleep(API_DELAY)
        else:
            logger.warning("tone_samples.txt 為空，使用預設指南")
            guidelines = "使用正體中文、台灣用語，語氣親切活潑，自稱小編。"

    # 直接爬網站並過濾
    done_urls = load_done_urls()
    all_articles = fetch_articles_from_websites()
    new_articles = [a for a in all_articles if a["url"] not in done_urls]

    logger.info(f"共 {len(all_articles)} 篇，其中 {len(new_articles)} 篇未處理")

    if not new_articles:
        logger.info("沒有新文章")
        tg_send_message("📭 沒有新文章")
        return

    # AI 選出高流量候選文章
    top_articles = rank_articles_by_traffic(client, new_articles, MAX_PER_RUN)
    time.sleep(API_DELAY)

    # 印出供審核
    print("\n" + "─" * 60)
    print(f"  AI 選出的 {len(top_articles)} 篇文章（請審核）")
    print("─" * 60)
    for i, a in enumerate(top_articles, 1):
        print(f"  {i}. [{a['source']}] {a['title']}")
        print(f"     {a['url']}")
    print("─" * 60)
    confirm = input("\n確認處理以上文章？[y/N] ").strip().lower()
    if confirm != "y":
        logger.info("已取消，結束程式")
        return

    today_str = datetime.now(TW_TZ).strftime("%Y-%m-%d")
    css = load_text("style.css")
    processed_urls = []

    for idx, article in enumerate(top_articles, 1):
        logger.info(f"[{idx}/{len(top_articles)}] 處理：{article['title']}")

        # 擷取全文（失敗用摘要）
        content = fetch_full_content(article["url"])
        if not content:
            logger.warning("全文擷取失敗，改用摘要")
            content = article.get("summary", "")
        if not content:
            logger.warning("無可用內容，略過此篇")
            continue

        try:
            # 改寫
            tone_samples = load_text("tone_samples.txt")
            raw = rewrite_article(client, article["title"], content, guidelines,
                                  css=css, tone_samples=tone_samples)
            time.sleep(API_DELAY)

            # 解析四個 tag
            title_m = re.search(r'<title>(.*?)</title>', raw, re.DOTALL)
            cont_m  = re.search(r'<content>(.*?)</content>', raw, re.DOTALL)
            zh_title   = title_m.group(1).strip() if title_m else article["title"]
            zh_content = cont_m.group(1).strip()  if cont_m  else raw
            # AI 有時會把外層 <div class="article-content"> 一起輸出，剝掉它
            _div_m = re.match(
                r'^\s*<div[^>]*class=["\']article-content["\'][^>]*>(.*)</div>\s*$',
                zh_content, re.DOTALL | re.IGNORECASE
            )
            if _div_m:
                zh_content = _div_m.group(1).strip()

            # 存 HTML
            filename = safe_filename(zh_title, today_str)
            filepath = os.path.join(OUTPUT_DIR, filename)
            save_text(filepath, build_html(
                title=zh_title,
                content=zh_content,
                source=article["source"],
                url=article["url"],
                date_str=today_str,
                css=css,
            ))
            logger.info(f"已儲存：{filepath}")

            # Telegram 通知 + 傳檔
            tg_send_message(
                f"📝 <b>新文章已生成</b>\n\n"
                f"標題：{article['title']}\n"
                f"來源：{article['source']}\n"
                f"原文：{article['url']}"
            )
            tg_send_file(filepath, caption=f"📄 {article['title'][:100]}")

            processed_urls.append(article["url"])

        except Exception as e:
            logger.error(f"處理失敗 {article['url']}：{e}")
            continue

    if processed_urls:
        save_done_urls(processed_urls)
        logger.info(f"done.txt 已更新，新增 {len(processed_urls)} 筆")


if __name__ == "__main__":
    main()
