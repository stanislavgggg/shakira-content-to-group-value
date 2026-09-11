"""
Мультиканальный новостной постер для Telegram.

Что делает:
  RSS -> жёсткий отсев -> эвристический балл -> оценка моделью (топ или нет)
      -> перевод на язык канала -> сверка чисел -> пост с картинкой.

Каналы, расписание и вертикали — в config.py. Источники — в feeds.py.

    python3 poster.py --check                      # живость фидов
    python3 poster.py --plan                       # что и когда постится
    python3 poster.py --preview luckyguru sports   # прогон без отправки
    python3 poster.py --once luckyguru sports      # один слот, с отправкой
    python3 poster.py --serve                      # демон с расписанием (Railway)

Переменные окружения: TG_BOT_TOKEN, ANTHROPIC_API_KEY, STATE_DIR, MIN_SCORE, DRY_RUN
"""

import os, re, io, json, time, random, argparse, hashlib, sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests, feedparser
from bs4 import BeautifulSoup

import config as C
import feeds as F

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
TG = f"https://api.telegram.org/bot{C.BOT_TOKEN}"


def log(*a):
    print(datetime.now(timezone.utc).strftime("%H:%M:%S"), *a, flush=True)


# ═══════════════════════════════════════════════════════════════════
#  СОСТОЯНИЕ
# ═══════════════════════════════════════════════════════════════════

def _path(name):
    os.makedirs(C.STATE_DIR, exist_ok=True)
    return os.path.join(C.STATE_DIR, name)


def load_json(name, default):
    try:
        with open(_path(name)) as f:
            return json.load(f)
    except Exception:
        return default


def save_json(name, data):
    tmp = _path(name) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, _path(name))


def load_seen(ch_key):
    """Дедуп на канал: одна и та же новость может уйти в LT и LV, но
    внутри канала — только один раз. Храним 800 последних uid."""
    return load_json(f"seen_{ch_key}.json", [])


def remember(ch_key, uid):
    seen = load_seen(ch_key)
    seen.append(uid)
    save_json(f"seen_{ch_key}.json", seen[-800:])


# ═══════════════════════════════════════════════════════════════════
#  СБОР ИЗ RSS
# ═══════════════════════════════════════════════════════════════════

def clean_html(html, limit=3000):
    txt = BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", txt)[:limit]


def entry_body(e):
    return clean_html((e.get("content") or [{}])[0].get("value") or e.get("summary", ""))


def entry_image(e):
    for k in ("media_content", "media_thumbnail"):
        m = e.get(k)
        if m and m[0].get("url"):
            return m[0]["url"]
    for link in e.get("links", []):
        if link.get("type", "").startswith("image/") and link.get("href"):
            return link["href"]
    raw = (e.get("content") or [{}])[0].get("value") or e.get("summary", "")
    img = BeautifulSoup(raw, "html.parser").find("img")
    return img["src"] if img and img.get("src") else None


def og_image(url):
    try:
        html = requests.get(url, headers=UA, timeout=20).text[:200000]
        soup = BeautifulSoup(html, "html.parser")
        for prop in ("og:image", "twitter:image"):
            t = (soup.find("meta", attrs={"property": prop})
                 or soup.find("meta", attrs={"name": prop}))
            if t and t.get("content", "").startswith("http"):
                return t["content"]
    except Exception:
        pass
    return None


def entry_age_hours(e):
    st = e.get("published_parsed") or e.get("updated_parsed")
    if not st:
        return None
    published = datetime(*st[:6], tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - published).total_seconds() / 3600


def domain(url):
    m = re.search(r"https?://(?:www\.)?([^/]+)", url or "")
    return m.group(1).lower() if m else ""


# ── жёсткий отсев ─────────────────────────────────────────────────

def rejected(title, link, body, age):
    if re.search(F.OPINION_START, title.strip(), re.I):
        return "колонка"
    if re.search(F.OPINION_PHRASE, title, re.I):
        return "колонка"
    if re.search(r"/(opinion|editorial|column|sponsored|partner-content)/", link, re.I):
        return "не новость"
    if len(body) < C.MIN_BODY:
        return "мало текста"
    if age is not None and age > C.MAX_AGE_HOURS:
        return f"старая ({age:.0f}ч)"
    return None


# ── эвристический балл (0-10), чтобы не гонять модель по мусору ───

def heuristic(item):
    score = F.TIER.get(domain(item["link"]), F.DEFAULT_TIER) * 1.5
    text = f"{item['title']} {item['body'][:400]}"

    for pat in F.STRONG_SIGNALS:
        if re.search(pat, text, re.I):
            score += 1.0
    for pat in F.WEAK_SIGNALS:
        if re.search(pat, item["title"], re.I):
            score -= 2.0

    age = item.get("age")
    if age is not None:
        if age <= 6:
            score += 2.0
        elif age <= 14:
            score += 1.0
        elif age > 24:
            score -= 1.0

    return score


def collect(vertical, ch_key):
    """Кандидаты по вертикали: отсев -> эвристический балл -> картинка."""
    seen = set(load_seen(ch_key))
    raw = []
    for url in F.FEEDS.get(vertical, []):
        try:
            d = feedparser.parse(url, request_headers=UA)
        except Exception as ex:
            log(f"  фид недоступен {url}: {ex}")
            continue
        for e in d.entries[:20]:
            link, title = e.get("link", ""), e.get("title", "")
            if not link or not title:
                continue
            uid = hashlib.md5((e.get("id") or link).encode()).hexdigest()[:16]
            if uid in seen:
                continue
            body, age = entry_body(e), entry_age_hours(e)
            if rejected(title, link, body, age):
                continue
            raw.append({"uid": uid, "title": title, "body": body, "link": link,
                        "age": age, "image": entry_image(e), "vertical": vertical})

    for it in raw:
        it["h"] = heuristic(it)
    raw.sort(key=lambda x: -x["h"])

    pool = []
    for it in raw:
        if len(pool) >= C.POOL_SIZE:
            break
        if not it["image"]:
            it["image"] = og_image(it["link"])
            time.sleep(0.2)
        if not it["image"]:
            continue
        pool.append(it)

    log(f"  [{vertical}] кандидатов {len(pool)} из {len(raw)} после отсева")
    return pool


# ═══════════════════════════════════════════════════════════════════
#  ВЫЗОВ МОДЕЛИ
# ═══════════════════════════════════════════════════════════════════

def anthropic(system, user, max_tokens=1200):
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": C.ANTHROPIC_KEY,
                 "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": C.MODEL, "max_tokens": max_tokens, "system": system,
              "messages": [{"role": "user", "content": user}]},
        timeout=120)
    if r.status_code != 200:
        try:
            err = r.json().get("error", {})
            raise RuntimeError(f"{r.status_code} {err.get('type')}: {err.get('message')}")
        except ValueError:
            raise RuntimeError(f"{r.status_code} {r.text[:300]}")
    txt = "".join(b.get("text", "") for b in r.json()["content"])
    return txt.replace("```json", "").replace("```", "").strip()


# ── ЭТАП 1: отбор топа ────────────────────────────────────────────

RANK_SYSTEM = """You are a news editor for a casino/sports Telegram channel. You score
candidate stories on how worth posting they are. You are strict: most feed items are
filler and should score low.

Score 0-100 on newsworthiness for this audience:
  85-100  major, concrete event the audience will talk about (big regulatory decision,
          major acquisition, big operator launch, major match result or transfer,
          record win, notable licence loss)
  70-84   solid real news with a concrete fact the audience cares about
  40-69   routine industry churn, minor appointments, small product updates
  0-39    listicles, guides, reviews, roundups, bonus-code SEO pages, opinion,
          re-reported old news, anything with no concrete new fact

Penalise heavily: no specific fact, promotional tone, "best X" framing, pure speculation.
Reward: named parties, hard numbers, a decision that actually happened, local relevance
to the market described in AUDIENCE.

Return JSON only, no fences, exactly:
{"ranked": [{"id": 1, "score": 88, "why": "six words max"}, ...]}
Include every candidate exactly once."""


def rank(items, ch):
    if not items:
        return []
    focus = ch.get("sports_focus", "")
    lines = []
    for i, it in enumerate(items, 1):
        age = f"{it['age']:.0f}h" if it.get("age") is not None else "?"
        lines.append(f"[{i}] ({age}, {domain(it['link'])}) {it['title']}\n"
                     f"    {it['body'][:280]}")
    user = (f"AUDIENCE: {C.LANGS[ch['lang']][1]}. "
            f"Sports relevance for this market: {focus}.\n\n"
            f"CANDIDATES:\n" + "\n".join(lines))

    try:
        data = json.loads(anthropic(RANK_SYSTEM, user, max_tokens=1500), strict=False)
        ranked = data.get("ranked", [])
    except Exception as ex:
        log(f"    оценка не удалась ({ex}) — падаем на эвристику")
        return sorted(items, key=lambda x: -x["h"])

    by_id = {r.get("id"): r for r in ranked if isinstance(r, dict)}
    out = []
    for i, it in enumerate(items, 1):
        r = by_id.get(i, {})
        it["score"] = int(r.get("score", 0) or 0)
        it["why"] = r.get("why", "")
        out.append(it)
    out.sort(key=lambda x: -x["score"])
    return out


# ── ЭТАП 2: перевод/чистка на язык канала ─────────────────────────

REWRITE_SYSTEM = """You turn one news item into a short Telegram post in {langname}.
You are NOT an editor — do not invent a hook, angle or structure.

RULES:
- Use ONLY facts present in the source text. Never invent a number, date, score,
  name or quote. If a fact is not in the source, it does not go in the post.
- Translate faithfully into natural {langname} as a native speaker would write it.
  Keep brand names, team names and competition names in their usual local form.
- Neutral news tone. No promotion, no calls to action, no invented excitement.
- Plain text only. No HTML, no markdown, no asterisks, no hashtags.
- title: max 90 characters. body: 2-4 sentences, max 500 characters.

Return JSON only, no fences, exactly:
{{"title": "...", "body": "..."}}"""


def rewrite(item, lang):
    langname = C.LANGS[lang][0]
    return json.loads(
        anthropic(REWRITE_SYSTEM.format(langname=langname),
                  f"HEADLINE: {item['title']}\n\nSOURCE TEXT:\n{item['body']}",
                  max_tokens=900),
        strict=False)


# ═══════════════════════════════════════════════════════════════════
#  СВЕРКА ЧИСЕЛ — защита от выдуманных цифр
# ═══════════════════════════════════════════════════════════════════

NUM = re.compile(r"\d[\d\s.,]*\d|\d")


def norm(s):
    s = s.replace(" ", "").replace("\u00a0", "")
    if s.count(",") == 1 and len(s.split(",")[1]) <= 2:
        s = s.replace(",", ".")
    else:
        s = s.replace(",", "")
    return s.rstrip(".").lstrip("0") or "0"


def numbers(text):
    return {norm(m) for m in NUM.findall(text)}


def audit(source, caption):
    invented = sorted(numbers(caption) - numbers(source), key=lambda x: (len(x), x))
    return [x for x in invented if x != "0" and len(x) > 1]


# ═══════════════════════════════════════════════════════════════════
#  ОФОРМЛЕНИЕ И ОТПРАВКА
# ═══════════════════════════════════════════════════════════════════

def esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_post(vertical, d):
    emoji = C.EMOJI.get(vertical, "📰")
    out = [f"{emoji} <b>{esc(d['title'])}</b>"]
    if d.get("body"):
        out.append(esc(d["body"]))
    return "\n\n".join(out)[:1024]


def keyboard(ch):
    link = ch.get("promo") or ""
    if not link:
        return None
    return {"inline_keyboard": [[{"text": ch.get("promo_text", "🎰"), "url": link}]]}


def send(ch, caption, image_url):
    kb = keyboard(ch)
    payload = {"chat_id": ch["chat_id"], "photo": image_url,
               "caption": caption, "parse_mode": "HTML"}
    if kb:
        payload["reply_markup"] = kb

    r = requests.post(f"{TG}/sendPhoto", json=payload, timeout=60).json()
    if r.get("ok"):
        return r["result"]["message_id"]

    # CDN закрыт хотлинком — качаем и шлём файлом
    img = requests.get(image_url, headers=UA, timeout=60)
    img.raise_for_status()
    data = {"chat_id": ch["chat_id"], "caption": caption, "parse_mode": "HTML"}
    if kb:
        data["reply_markup"] = json.dumps(kb)
    r = requests.post(f"{TG}/sendPhoto", data=data,
                      files={"photo": ("p.jpg", io.BytesIO(img.content), "image/jpeg")},
                      timeout=120).json()
    if not r.get("ok"):
        raise RuntimeError(r.get("description"))
    return r["result"]["message_id"]


# ═══════════════════════════════════════════════════════════════════
#  СЛОТ
# ═══════════════════════════════════════════════════════════════════

def run_slot(ch_key, vertical, do_post=True, count=None):
    ch = C.CHANNELS[ch_key]
    count = count or C.PER_SLOT
    log(f"── {ch['title']} / {vertical} ──")

    pool = collect(vertical, ch_key)
    if not pool:
        log("    кандидатов нет, слот пропущен")
        return 0

    ranked = rank(pool, ch)
    top = [it for it in ranked if it.get("score", 0) >= C.MIN_SCORE]
    log(f"    выше порога {C.MIN_SCORE}: {len(top)} из {len(ranked)}"
        f" (лучший балл {ranked[0].get('score', '-')})")
    if not top:
        log("    ничего топового — лучше молчать, чем лить проходняк")
        return 0

    posted = 0
    for it in top:
        if posted >= count:
            break
        log(f"    [{it.get('score')}] {it['title'][:70]}  — {it.get('why','')}")
        try:
            data = rewrite(it, ch["lang"])
            cap = format_post(vertical, data)
        except Exception as ex:
            log(f"      перевод не удался: {ex}")
            continue

        bad = audit(it["body"], cap)
        if bad:
            log(f"      ПРОПУСК: числа не из источника ({', '.join(bad)})")
            continue

        print("\n" + cap + "\n", flush=True)

        if not do_post or C.DRY_RUN:
            posted += 1
            continue

        try:
            mid = send(ch, cap, it["image"])
            remember(ch_key, it["uid"])
            log(f"      → отправлено #{mid}")
            posted += 1
        except Exception as ex:
            log(f"      → ошибка отправки: {ex}")
        time.sleep(random.uniform(3, 6))

    if posted == 0:
        log("    ничего не ушло")
    return posted


# ═══════════════════════════════════════════════════════════════════
#  РАСПИСАНИЕ
# ═══════════════════════════════════════════════════════════════════

CATCHUP_MIN = 55   # если контейнер перезапустился — досылаем слот в течение часа


def due_slots(now_utc, fired):
    """Возвращает (ch_key, vertical, marker) для слотов, которым пора."""
    out = []
    for ch_key, ch in C.CHANNELS.items():
        local = now_utc.astimezone(ZoneInfo(ch["tz"]))
        for hhmm, vertical in ch["schedule"]:
            h, m = (int(x) for x in hhmm.split(":"))
            slot = local.replace(hour=h, minute=m, second=0, microsecond=0)
            if local < slot:
                continue
            if (local - slot) > timedelta(minutes=CATCHUP_MIN):
                continue
            marker = f"{ch_key}|{hhmm}|{vertical}|{local:%Y-%m-%d}"
            if fired.get(marker):
                continue
            out.append((ch_key, vertical, marker))
    return out


def tick():
    """Один проход: отработать слоты, которым пора, и выйти.
    Используется и демоном, и Railway cron."""
    fired = load_json("fired.json", {})
    due = due_slots(datetime.now(timezone.utc), fired)
    if not due:
        return 0
    for ch_key, vertical, marker in due:
        try:
            run_slot(ch_key, vertical, do_post=True)
        except Exception as ex:
            log(f"слот {marker} упал: {ex}")
        fired[marker] = int(time.time())
        cutoff = int(time.time()) - 10 * 86400
        fired = {k: v for k, v in fired.items() if v > cutoff}
        save_json("fired.json", fired)
    return len(due)


def serve():
    preflight()
    log(f"старт. каналов {len(C.CHANNELS)}, "
        f"порог {C.MIN_SCORE}, state {C.STATE_DIR}"
        f"{', DRY_RUN' if C.DRY_RUN else ''}")
    plan()
    while True:
        try:
            tick()
        except Exception as ex:
            log(f"цикл упал: {ex}")
        time.sleep(45)


def plan():
    rows = []
    for ch_key, ch in C.CHANNELS.items():
        local = datetime.now(timezone.utc).astimezone(ZoneInfo(ch["tz"]))
        for hhmm, vertical in ch["schedule"]:
            rows.append((hhmm, ch["tz"], ch["title"], vertical))
    rows.sort()
    print("\nрасписание (время локальное для канала):")
    for hhmm, tz, title, vertical in rows:
        print(f"  {hhmm}  {tz:16} {title:18} {vertical}")
    print(f"\nвсего {len(rows)} слотов в сутки, по {C.PER_SLOT} посту за слот\n")


# ═══════════════════════════════════════════════════════════════════
#  ПРОВЕРКИ
# ═══════════════════════════════════════════════════════════════════

def preflight():
    if not C.BOT_TOKEN:
        raise SystemExit("TG_BOT_TOKEN не задан")
    if not C.ANTHROPIC_KEY.startswith("sk-ant-"):
        raise SystemExit("ANTHROPIC_API_KEY не задан или не похож на ключ")
    for ch_key, ch in C.CHANNELS.items():
        if C.DRY_RUN:
            continue
        r = requests.post(f"{TG}/getChat",
                          json={"chat_id": ch["chat_id"]}, timeout=30).json()
        if not r.get("ok"):
            raise SystemExit(f"канал {ch['title']} ({ch['chat_id']}) недоступен: "
                             f"{r.get('description')} — добавь бота админом")
        log(f"канал OK: {ch['title']}")


def check_feeds():
    for vertical, urls in F.FEEDS.items():
        print(f"── {vertical} ──")
        for url in urls:
            try:
                d = feedparser.parse(url, request_headers=UA)
                n = len(d.entries)
                if not n:
                    print(f"  DEAD      {url}")
                    continue
                imgs = sum(1 for e in d.entries[:5] if entry_image(e))
                dated = sum(1 for e in d.entries[:5]
                            if entry_age_hours(e) is not None)
                print(f"  OK {n:3}    {url}   картинки {imgs}/5  даты {dated}/5")
            except Exception as ex:
                print(f"  ERR       {url}  {ex}")
        print()


# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="проверить фиды")
    ap.add_argument("--plan", action="store_true", help="показать расписание")
    ap.add_argument("--preview", nargs=2, metavar=("CHANNEL", "VERTICAL"))
    ap.add_argument("--once", nargs=2, metavar=("CHANNEL", "VERTICAL"))
    ap.add_argument("--serve", action="store_true", help="демон с расписанием")
    ap.add_argument("--tick", action="store_true",
                    help="один проход по расписанию и выход (для Railway cron)")
    ap.add_argument("-n", type=int, default=None, help="сколько постов за прогон")
    a = ap.parse_args()

    def resolve(key):
        if key not in C.CHANNELS:
            raise SystemExit(f"нет канала {key}. Есть: {', '.join(C.CHANNELS)}")
        return key

    if a.check:
        check_feeds()
    elif a.plan:
        plan()
    elif a.preview:
        run_slot(resolve(a.preview[0]), a.preview[1], do_post=False, count=a.n)
    elif a.once:
        preflight()
        run_slot(resolve(a.once[0]), a.once[1], do_post=True, count=a.n)
    elif a.tick:
        preflight()
        n = tick()
        log(f"слотов отработано: {n}")
    elif a.serve:
        serve()
    else:
        print(__doc__)
