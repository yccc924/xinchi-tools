import os
from dotenv import load_dotenv

load_dotenv()

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# 使用哪個 provider：gemini 或 nvidia
PROVIDER = os.getenv("PROVIDER", "gemini")

# NVIDIA 可選模型：
#   mistralai/mistral-large-3-675b   ← 範例使用，結構遵守最穩定
#   deepseek-ai/deepseek-v4-pro      ← 中文品質佳
NVIDIA_MODEL = os.getenv("MODEL", "mistralai/mistral-large-3-675b")

# Gemini 模型
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

RSS_FEEDS = [
    "https://www.macworld.com/feed",
    "https://9to5mac.com/feed",
    "https://www.macrumors.com/macrumors.xml",
]

WEBSITE_SOURCES = [
    {"url": "https://www.macworld.com/", "name": "Macworld"},
    {"url": "https://9to5mac.com/", "name": "9to5Mac"},
    {"url": "https://www.macrumors.com/", "name": "MacRumors"},
]

DONE_FILE = "done.txt"
PROMPT_FILE = "prompt.md"
TONE_SAMPLES_FILE = "tone_samples.txt"
OUTPUT_DIR = "output"

API_DELAY = 2           # 秒，避免超過 40 RPM 限制
TELEGRAM_RETRY_DELAY = 30  # 秒，Telegram 重試等待
MAX_PER_RUN = 5         # 每次最多處理篇數
