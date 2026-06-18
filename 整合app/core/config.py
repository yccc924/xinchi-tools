import json
from pathlib import Path

_PATH = Path(__file__).parent.parent / 'config.json'


def load() -> dict:
    if _PATH.exists():
        try:
            return json.loads(_PATH.read_text(encoding='utf-8'))
        except Exception:
            return {}
    return {}


def update(data: dict):
    current = load()
    current.update(data)
    _PATH.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding='utf-8')
