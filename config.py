"""
Конфиг постера. Здесь лежит всё, что меняется руками.
Логика — в poster.py, её трогать не нужно.
"""

import os

# ═══════════════════════════════════════════════════════════════════
#  ОКРУЖЕНИЕ (задаётся переменными в Railway)
# ═══════════════════════════════════════════════════════════════════

BOT_TOKEN     = os.getenv("TG_BOT_TOKEN", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL         = os.getenv("MODEL", "claude-sonnet-5")

# Каталог для seen/fired. На Railway смонтируй volume и поставь STATE_DIR=/data,
# иначе после каждого редеплоя бот забудет, что уже постил.
STATE_DIR = os.getenv("STATE_DIR", "./state")

# DRY_RUN=1 — всё считает и печатает, но в Telegram ничего не шлёт.
DRY_RUN = os.getenv("DRY_RUN", "") == "1"


# ═══════════════════════════════════════════════════════════════════
#  ПОРОГ «ТОПОВОСТИ»
# ═══════════════════════════════════════════════════════════════════

# Модель оценивает каждого кандидата 0-100. Ниже порога — не постим вообще,
# лучше пропустить слот, чем залить проходную новость.
MIN_SCORE = int(os.getenv("MIN_SCORE", "72"))

POOL_SIZE     = 14   # сколько кандидатов уходит на оценку модели
MAX_AGE_HOURS = 36   # старше — не рассматриваем
MIN_BODY      = 220  # короче — в фиде огрызок, толку нет
PER_SLOT      = 1    # постов за слот


# ═══════════════════════════════════════════════════════════════════
#  КАНАЛЫ И РАСПИСАНИЕ
# ═══════════════════════════════════════════════════════════════════
#
#  schedule — список (время, вертикаль). Время ЛОКАЛЬНОЕ для канала (поле tz).
#  Вертикали: sports | industry | casino | gaming  (фиды — в feeds.py)
#
#  sports_focus — подсказка модели при отборе: какие виды спорта важны рынку.
#                 Не фильтр, а вес при оценке.
#
#  promo / promo_text — кнопка под постом. Пустой promo = без кнопки.
#                       ВПИШИ СЮДА ТРЕКИНГОВЫЕ ССЫЛКИ КАНАЛОВ.
#
CHANNELS = {

    "luckyguru": {
        "title":        "LUCKY GURU",
        "handle":       "@luckycasinoguru",
        "chat_id":      "-1003237183860",
        "lang":         "lt",
        "tz":           "Europe/Vilnius",
        "sports_focus": "basketball (LKL, Žalgiris, Euroleague, NBA) first, then football",
        "promo":        "",
        "promo_text":   "🎰 Žaisti dabar",
        "schedule": [
            ("09:00", "sports"),
            ("13:00", "industry"),
            ("19:00", "casino"),
        ],
    },

    "luckylatvia": {
        "title":        "LUCKY LATVIA",
        "handle":       "@luckylatviaan",
        "chat_id":      "-1003910322335",
        "lang":         "lv",
        "tz":           "Europe/Riga",
        "sports_focus": "ice hockey and basketball first, then football",
        "promo":        "",
        "promo_text":   "🎰 Spēlēt tagad",
        "schedule": [
            ("09:00", "sports"),
            ("13:00", "industry"),
            ("19:00", "casino"),
        ],
    },

    "luckybulgaria": {
        "title":        "КЪСМЕТ БЪЛГАРИЯ",
        "handle":       "@luckybulgaria",
        "chat_id":      "-1004493433117",
        "lang":         "bg",
        "tz":           "Europe/Sofia",
        "sports_focus": "football first (domestic and big European leagues), then volleyball",
        "promo":        "",
        "promo_text":   "🎰 Играй сега",
        "schedule": [
            ("09:00", "sports"),
            ("13:00", "industry"),
            ("19:00", "casino"),
        ],
    },

    "balkanjackpot": {
        "title":        "BALKAN JACKPOT",
        "handle":       "@balkanjackpot",
        "chat_id":      "-1003522266492",
        "lang":         "hr",
        "tz":           "Europe/Zagreb",
        "sports_focus": "football first (HNL, Dinamo, Hajduk, big European leagues), then basketball",
        "promo":        "",
        "promo_text":   "🎰 Igraj sada",
        "schedule": [
            ("09:00", "sports"),
            ("13:00", "industry"),
            ("19:00", "casino"),
        ],
    },
}


# ═══════════════════════════════════════════════════════════════════
#  ЯЗЫКИ
# ═══════════════════════════════════════════════════════════════════

LANGS = {
    "en": ("English",    "a general iGaming audience"),
    "lt": ("Lithuanian", "a Lithuanian casino and sports audience"),
    "lv": ("Latvian",    "a Latvian casino and sports audience"),
    "bg": ("Bulgarian",  "a Bulgarian casino and sports audience"),
    "hr": ("Croatian",   "a Croatian casino and sports audience"),
}

EMOJI = {
    "sports":   "⚽",
    "industry": "🏢",
    "casino":   "🎰",
    "gaming":   "🎮",
}
