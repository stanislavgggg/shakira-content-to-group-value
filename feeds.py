"""
Источники по вертикалям + вес источника.

TIER — насколько источнику доверяем. Идёт в эвристический балл до того,
как кандидаты уйдут на оценку модели:
    3 — отраслевые первоисточники, редко пишут мусор
    2 — нормальные новостники
    1 — много SEO-подобного контента, берём осторожно
"""

FEEDS = {
    "casino": [
        "https://www.casino.org/news/feed/",
        "https://casinoreports.ca/feed/",
        "https://www.slotbeats.com/category/latest-slots/feed/",
        "https://www.bigwinboard.com/feed/",
        "https://www.vegasslotsonline.com/news/feed/",
    ],
    "industry": [
        "https://igamingbusiness.com/feed/",
        "https://sbcnews.co.uk/feed/",
        "https://casinobeats.com/feed/",
        "https://www.gamblinginsider.com/rss",
        "https://calvinayre.com/feed/",
        "https://www.gamblingnews.com/feed/",
    ],
    # Футбол + баскетбол + хоккей. Рынки разные: LT смотрит баскетбол,
    # LV хоккей, BG и HR футбол. Один общий пул, приоритет задаётся
    # через sports_focus канала в config.py.
    "sports": [
        # футбол
        "https://www.theguardian.com/football/rss",
        "https://feeds.bbci.co.uk/sport/rss.xml",
        "https://www.skysports.com/rss/12040",
        "https://www.90min.com/posts.rss",
        # баскетбол
        "https://www.espn.com/espn/rss/nba/news",
        "https://www.eurohoops.net/en/feed/",
        # хоккей
        "https://www.espn.com/espn/rss/nhl/news",
        # общий
        "https://www.espn.com/espn/rss/news",
    ],
    "gaming": [
        "https://www.pcgamer.com/rss/",
        "https://www.eurogamer.net/feed",
        "https://www.vg247.com/feed",
        "https://gamerant.com/feed/",
    ],
}

TIER = {
    "igamingbusiness.com":  3,
    "sbcnews.co.uk":        3,
    "casinobeats.com":      3,
    "gamblinginsider.com":  3,
    "casino.org":           2,
    "gamblingnews.com":     2,
    "calvinayre.com":       2,
    "casinoreports.ca":     2,
    "slotbeats.com":        2,
    "bigwinboard.com":      1,
    "vegasslotsonline.com": 1,
    "livecasino24.com":     1,
    "skysports.com":        3,
    "espn.com":             3,
    "eurohoops.net":        3,
    "90min.com":            1,
    "theguardian.com":      3,
    "bbci.co.uk":           3,
    "pcgamer.com":          2,
    "eurogamer.net":        2,
    "vg247.com":            2,
    "gamerant.com":         1,
}

DEFAULT_TIER = 1


# ── сигналы «это настоящая новость» ───────────────────────────────
# Регуляторка, деньги, сделки, запуски, результаты — то, что реально
# произошло, а не обзор/подборка.
STRONG_SIGNALS = [
    r"\b(acquir|merger|takeover|buys?|sold|stake)\b",
    r"\b(licen[cs]e|regulat|ban|fine|penalt|court|lawsuit|ruling)\b",
    r"\b(launch|goes live|debut|rollout|partners? with|partnership|deal)\b",
    r"\b(revenue|profit|results|earnings|quarter|Q[1-4]\b|record)\b",
    r"[€$£]\s?\d",
    r"\b\d+(\.\d+)?\s?(m|bn|million|billion)\b",
    r"\b(signs?|transfer|injur|sacked|appointed|wins?|beat|defeat)\b",
]

# ── сигналы «это SEO-мусор / подборка / обзор» ────────────────────
WEAK_SIGNALS = [
    r"\b(best|top \d+|guide|how to|tips|tricks|everything you need)\b",
    r"\b(review|preview of|ranked|ultimate|complete list)\b",
    r"\b(bonus code|promo code|free spins? offer|no deposit)\b",
    r"\b(horoscope|quiz|things? you)\b",
]

# ── личные колонки: по тону не годятся для новостного поста ───────
OPINION_START = r"^(i['’]m|i've|i am|i was|i think|my|we['’]re|we are|our)\b"
OPINION_PHRASE = (r"\b(my reaction|my thoughts|my take|untangling my|opinion|"
                  r"editorial|column|i literally|i recoiled)\b")
