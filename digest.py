"""
Market Digest — תמונת סיכום שוק יומית לדיסקורד.

מריצים:
    python digest.py              # מצב רגיל (כמו ב-GitHub Actions)
    python digest.py --force      # בלי בדיקת שעה (לבדיקות)
    python digest.py --demo       # נתוני דמו, בלי אינטרנט
    python digest.py --no-send    # רק שומר את התמונה, לא שולח
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from zoneinfo import ZoneInfo

import requests
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

ROOT = Path(__file__).parent
OUT_DIR = ROOT / "out"
ET = ZoneInfo("America/New_York")
GENERAL = "כללי"

# המשבצות בחלק התחתון (שתי שורות של 4)
MARKET_TILES = [
    {"symbol": "^GSPC", "label": "S&P 500", "sub": "", "kind": "index"},
    {"symbol": "^IXIC", "label": "NASDAQ", "sub": "", "kind": "index"},
    {"symbol": "^VIX", "label": "VIX", "sub": "", "kind": "vix"},
    {"symbol": "^RUT", "label": "RUSSELL", "sub": "", "kind": "index"},
    {"symbol": "RSP", "label": "RSP", "sub": "שוויוני", "kind": "price"},
    {"symbol": "BTC-USD", "label": "BITCOIN", "sub": "", "kind": "crypto"},
    {"symbol": "CL=F", "label": "USOIL", "sub": "", "kind": "price"},
    {"symbol": "^TNX", "label": "US10Y", "sub": "", "kind": "yield"},
]

# צבע רקע לפי ה-S&P 500
MOODS = [  # (סף מינימלי, שם)
    (1.0, "strong-up"),
    (0.25, "up"),
    (-0.25, "flat"),
    (-1.0, "down"),
    (float("-inf"), "strong-down"),
]


@dataclass
class Quote:
    symbol: str
    price: float
    prev: float
    group: str = GENERAL

    @property
    def chg(self) -> float:
        return (self.price / self.prev - 1) * 100 if self.prev else 0.0


# ───────────────────────────── נתונים ─────────────────────────────

def load_config() -> dict:
    cfg = yaml.safe_load((ROOT / "watchlist.yaml").read_text(encoding="utf-8"))
    groups = cfg.get("groups") or {}
    watch: dict[str, str] = {}
    for group, tickers in groups.items():
        for t in tickers or []:
            watch[str(t).strip().upper()] = str(group)
    for t in cfg.get("tickers") or []:  # רשימה שטוחה (אופציונלי)
        watch.setdefault(str(t).strip().upper(), GENERAL)
    if not watch:
        sys.exit("watchlist.yaml ריק — צריך להוסיף לפחות מניה אחת")
    cfg["watch"] = watch
    return cfg


def fetch_quotes(symbols: list[str], today: dt.date) -> tuple[dict[str, Quote], dt.date]:
    """מוריד נתונים יומיים מ-Yahoo. בשעות המסחר, הנר של היום = המחיר הנוכחי."""
    import pandas as pd
    import yfinance as yf

    data = None
    for attempt in range(3):
        try:
            data = yf.download(
                symbols, period="10d", interval="1d", group_by="ticker",
                auto_adjust=False, progress=False, threads=True,
            )
            if data is not None and not data.empty:
                break
        except Exception as e:  # yfinance לפעמים נחסם זמנית
            print(f"ניסיון {attempt + 1} נכשל: {e}")
        time.sleep(15)
    if data is None or data.empty:
        sys.exit("לא התקבלו נתונים מ-Yahoo Finance")

    def closes(sym: str) -> "pd.Series":
        try:
            s = data[sym]["Close"] if isinstance(data.columns, pd.MultiIndex) else data["Close"]
        except KeyError:
            return pd.Series(dtype=float)
        s = s.dropna()
        s.index = [d.date() for d in pd.to_datetime(s.index)]
        return s

    spx = closes("^GSPC")
    if spx.empty:
        sys.exit("אין נתונים ל-S&P 500")
    session = max(spx.index)  # יום המסחר האחרון (היום, אם הבורסה פתוחה)

    quotes: dict[str, Quote] = {}
    for sym in symbols:
        s = closes(sym)
        before = s[[d < session for d in s.index]]
        if s.empty or before.empty:
            print(f"⚠️  אין מספיק נתונים ל-{sym}, מדלג")
            continue
        on_session = s[[d == session for d in s.index]]
        if on_session.empty:
            print(f"⚠️  אין מחיר עדכני ל-{sym} ליום {session}, מדלג (לא מציג נתון ישן)")
            continue
        quotes[sym] = Quote(sym, float(on_session.iloc[-1]), float(before.iloc[-1]))

    # יומן אימות: כל מחיר שנכנס לתמונה, כדי שאפשר יהיה להשוות מול Yahoo
    print(f"\nנתונים מ-Yahoo Finance ליום {session}:")
    print(f"{'SYMBOL':<9}{'PREV CLOSE':>12}{'NOW':>12}{'CHANGE':>9}")
    for q in quotes.values():
        print(f"{q.symbol:<9}{q.prev:>12,.2f}{q.price:>12,.2f}{q.chg:>+8.2f}%")
    print()
    return quotes, session


def demo_quotes() -> dict[str, Quote]:
    rows = {
        "NVDA": (212.5, 3.9), "AVGO": (402.1, 2.8), "AMD": (188.0, 4.6), "SOXX": (290.3, 3.1),
        "AAPL": (241.0, 0.4), "GOOGL": (228.0, 1.2), "AMZN": (238.0, 0.6), "META": (744.0, -1.1),
        "MSFT": (512.0, -0.8), "TSLA": (402.0, 2.2), "MAGS": (61.2, 0.9),
        "PLTR": (171.0, -4.1), "NOW": (880.3, -2.9), "IGV": (108.4, -1.9),
        "GEV": (655.0, 1.7), "SPCX": (148.7, -2.4), "WGMI": (31.4, 5.8),
        "^GSPC": (7292, 0.35), "^IXIC": (25311, 0.56), "^VIX": (21.93, -1.31), "^RUT": (2875, 1.39),
        "RSP": (192.4, 0.92), "BTC-USD": (118420, -3.4), "CL=F": (71.35, 2.4),
    }
    q = {s: Quote(s, p, p / (1 + c / 100)) for s, (p, c) in rows.items()}
    q["^TNX"] = Quote("^TNX", 4.31, 4.24)
    return q


# ───────────────────────────── טקסט בעברית ─────────────────────────────

def tk(sym: str) -> Markup:
    """סימול/מספר בכיוון LTR בתוך טקסט עברי."""
    return Markup('<bdi class="tk">{}</bdi>').format(sym)


def pct(x: float, sign: bool = False) -> Markup:
    return tk(f"{x:+.2f}%" if sign else f"{abs(x):.2f}%")


def verb_plural(c: float) -> str:  # "מניות X ..."
    if c >= 4: return "זינקו"
    if c >= 1.5: return "מטפסות"
    if c > 0: return "מתחזקות"
    if c <= -4: return "צנחו"
    if c <= -1.5: return "יורדות"
    return "נחלשות"


def verb_single(c: float) -> str:  # "X מזנקת ..."
    if c >= 4: return "מזנקת"
    if c >= 1.5: return "מטפסת"
    if c >= 0: return "עולה"
    if c <= -4: return "צונחת"
    if c <= -1.5: return "יורדת"
    return "נחלשת"


def verb_masc(c: float) -> str:  # ביטקוין / נפט / מדד
    if c >= 4: return "מזנק"
    if c >= 0: return "עולה"
    if c <= -4: return "צונח"
    return "יורד"


def build_headline(stocks: list[Quote]) -> tuple[Markup, str]:
    ups = sorted([s for s in stocks if s.chg > 0], key=lambda s: -s.chg)
    downs = sorted([s for s in stocks if s.chg < 0], key=lambda s: s.chg)
    if not ups and not downs:
        return Markup("שעת המסחר הראשונה: הרשימה ללא שינוי"), "flat"

    focus_up = bool(ups) and (not downs or ups[0].chg >= abs(downs[0].chg))
    movers = ups if focus_up else downs
    tone = "up" if focus_up else "down"
    lead = movers[0]
    hl = lambda text: Markup('<span class="hl">{}</span>').format(text)

    if lead.group != GENERAL:
        same = [s for s in movers if s.group == lead.group]
        if len(same) >= 2:
            avg = mean(s.chg for s in same[:3])
            return (Markup("מניות ") + hl(lead.group) + " " + verb_plural(avg)
                    + " בהובלת " + tk(same[0].symbol) + " ו-" + tk(same[1].symbol)), tone

    if len(movers) >= 2 and abs(movers[1].chg) >= 0.6 * abs(lead.chg):
        word = "העליות" if focus_up else "הירידות"
        return (tk(lead.symbol) + " ו-" + tk(movers[1].symbol) + " מובילות את " + hl(word)), tone

    return tk(lead.symbol) + " " + hl(verb_single(lead.chg)) + " ב-" + pct(lead.chg), tone


def build_story(stocks: list[Quote], mkt: dict[str, Quote]) -> Markup:
    parts: list[Markup] = []
    ups = sorted([s for s in stocks if s.chg > 0], key=lambda s: -s.chg)
    downs = sorted([s for s in stocks if s.chg < 0], key=lambda s: s.chg)

    # 1. מצב השוק
    spx, ndx = mkt.get("^GSPC"), mkt.get("^IXIC")
    if spx and ndx:
        w = lambda c: "עולה" if c >= 0 else "יורד"
        if (spx.chg >= 0) == (ndx.chg >= 0):
            direction = "בעליות" if spx.chg >= 0 else "בירידות"
            parts.append(Markup("וול סטריט נסחרת {}: ה-{} {} ב-{} והנאסד״ק ב-{}.").format(
                direction, tk("S&P 500"), w(spx.chg), pct(spx.chg), pct(ndx.chg)))
        else:
            parts.append(Markup("וול סטריט נסחרת במגמה מעורבת: ה-{} {} ב-{} והנאסד״ק {} ב-{}.").format(
                tk("S&P 500"), w(spx.chg), pct(spx.chg), w(ndx.chg), pct(ndx.chg)))

    # 2. המובילות
    if ups:
        s = Markup("בראש הרשימה {} עם עלייה של {}").format(tk(ups[0].symbol), pct(ups[0].chg))
        rest = [Markup("{} ({})").format(tk(q.symbol), pct(q.chg, sign=True)) for q in ups[1:3]]
        if rest:
            s += Markup(", ואחריה ") + Markup(" ו-").join(rest)
        parts.append(s + ".")
    elif downs:
        parts.append(Markup("כל המניות ברשימה נסחרות היום בירידות."))
    else:
        parts.append(Markup("המניות ברשימה נסחרות ללא שינוי מהותי."))

    # 3. החלשות
    if downs:
        opener = "מנגד," if ups else "בראש הירידות"
        s = Markup("{} {} {} ב-{}").format(opener, tk(downs[0].symbol), verb_single(downs[0].chg), pct(downs[0].chg))
        if len(downs) >= 2:
            s += Markup(" ו-{} ב-{}").format(tk(downs[1].symbol), pct(downs[1].chg))
        parts.append(s + ".")
    elif ups:
        parts.append(Markup("כל המניות ברשימה נסחרות היום בעליות."))

    # 4. רוחב שוק (RSP מול S&P)
    rsp = mkt.get("RSP")
    if rsp and spx:
        d = rsp.chg - spx.chg
        if d >= 0.4:
            parts.append(Markup("רוחב השוק חיובי: ה-{} השוויוני ({}) מקדים את המדד המשוקלל בכ-{}.").format(
                tk("S&P"), tk("RSP"), pct(d)))
        elif d <= -0.4:
            parts.append(Markup("המדד נשען על הענקיות: ה-{} השוויוני ({}) מפגר אחרי המדד המשוקלל בכ-{}.").format(
                tk("S&P"), tk("RSP"), pct(d)))

    # 5. רוטציה בין קבוצות
    by_group: dict[str, list[float]] = {}
    for s in stocks:
        if s.group != GENERAL:
            by_group.setdefault(s.group, []).append(s.chg)
    avgs = {g: mean(v) for g, v in by_group.items() if len(v) >= 2}
    if len(avgs) >= 2:
        best = max(avgs, key=avgs.get)
        worst = min(avgs, key=avgs.get)
        if avgs[best] >= 1 and avgs[worst] <= -1:
            parts.append(Markup("המגמה מעידה על מעבר ממניות {} אל מניות {}.").format(worst, best))

    # 6. מאקרו — רק כשיש תנועה משמעותית
    btc, oil, tnx = mkt.get("BTC-USD"), mkt.get("CL=F"), mkt.get("^TNX")
    if btc and abs(btc.chg) >= 3:
        parts.append(Markup("הביטקוין {} ב-{}.").format(verb_masc(btc.chg), pct(btc.chg)))
    if oil and abs(oil.chg) >= 2:
        parts.append(Markup("הנפט {} ב-{}.").format(verb_masc(oil.chg), pct(oil.chg)))
    if tnx and abs(tnx.price - tnx.prev) * 100 >= 5:
        parts.append(Markup("תשואת האג״ח ל-10 שנים {} ל-{}.").format(
            "עולה" if tnx.price > tnx.prev else "יורדת", tk(f"{tnx.price:.2f}%")))

    return Markup(" ").join(parts[:6])  # לא יותר מ-6 משפטים


# ───────────────────────────── עיצוב ─────────────────────────────

def mood_for(spx_chg: float) -> str:
    for threshold, name in MOODS:
        if spx_chg >= threshold:
            return name
    return "flat"


def direction(c: float, invert: bool = False) -> str:
    if abs(c) < 0.005:
        return "flat"
    up = c > 0
    return "up" if up != invert else "down"


def fmt_price(v: float, kind: str) -> str:
    if kind == "yield":
        return f"{v:.2f}%"
    if kind == "crypto":
        return f"${v:,.0f}"
    return f"{v:,.0f}" if v >= 1000 else f"{v:,.2f}"


def build_tiles(mkt: dict[str, Quote]) -> list[dict]:
    tiles = []
    for t in MARKET_TILES:
        q = mkt.get(t["symbol"])
        if not q:
            continue
        if t["kind"] == "yield":
            bps = (q.price - q.prev) * 100
            change, cls = f"{bps:+.0f} bps", direction(bps)
        else:
            change, cls = f"{q.chg:+.2f}%", direction(q.chg, invert=t["kind"] == "vix")
        value_cls = ""
        if t["kind"] == "vix":
            value_cls = "danger" if q.price >= 30 else "warn" if q.price >= 20 else ""
        tiles.append({**t, "value": fmt_price(q.price, t["kind"]), "change": change,
                      "cls": cls, "value_cls": value_cls})
    return tiles


def vix_alert(mkt: dict[str, Quote]) -> dict | None:
    """הודעת VIX: שורה ראשונה = כותרת, השאר = שורות משנה."""
    vix = mkt.get("^VIX")
    if not vix:
        return None
    if vix.price > 30:
        return {"level": "danger", "title": "Vix > 30",
                "lines": ["קנייה🛒🛒🛒", "קנייה גם כשמגעיל"]}
    if vix.price > 20:
        return {"level": "warn", "title": "Vix > 20 🛒",
                "lines": ["סטטיסטיקה לטובתנו 🛒"]}
    return {"level": "calm", "title": "",
            "lines": [Markup("רמת {} ב-{}: השוק רגוע יחסית").format(tk("VIX"), tk(f"{vix.price:.2f}"))]}


def stock_rows(quotes: list[Quote]) -> list[dict]:
    return [{"symbol": q.symbol, "change": f"{q.chg:+.2f}%", "cls": direction(q.chg),
             "group": "" if q.group == GENERAL else q.group, "price": fmt_price(q.price, "price")}
            for q in quotes]


def render_html(ctx: dict) -> str:
    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape(["html"]))
    return env.get_template("digest.html").render(**ctx)


def html_to_png(html: str, out: Path) -> None:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1080, "height": 1350}, device_scale_factor=1)
        page.set_content(html, wait_until="networkidle", timeout=30000)
        page.evaluate("() => document.fonts.ready.then(() => true)")
        page.locator("#card").screenshot(path=str(out))
        browser.close()


def send_discord(url: str, png: Path, text: str) -> None:
    with png.open("rb") as f:
        r = requests.post(url, data={"payload_json": json.dumps({"content": text})},
                          files={"files[0]": (png.name, f, "image/png")}, timeout=30)
    r.raise_for_status()
    print("✅ נשלח לדיסקורד")


# ───────────────────────────── ריצה ─────────────────────────────

def should_run(now: dt.datetime, schedule: str) -> bool:
    """שני cron-ים (קיץ/חורף) — רק אחד מהם מתאים לשעון הנוכחי בניו יורק."""
    if now.weekday() >= 5:
        print("סוף שבוע — אין מסחר")
        return False
    if now.hour > 12 or (now.hour == 12 and now.minute > 30):
        print(f"מאוחר מדי ({now:%H:%M %Z}): הריצה התעכבה, לא שולח תמונה של אמצע היום בשעה לא נכונה")
        return False
    if schedule:
        is_dst = bool(now.dst())
        summer_cron = schedule.strip().startswith("30 14")
        if is_dst != summer_cron:
            print(f"ה-cron '{schedule}' לא מתאים לשעון הנוכחי ({now:%H:%M %Z}) — מדלג")
            return False
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="בלי בדיקות שעה/יום מסחר")
    ap.add_argument("--demo", action="store_true", help="נתוני דמו")
    ap.add_argument("--no-send", action="store_true", help="לא לשלוח לדיסקורד")
    args = ap.parse_args()
    force = args.force or args.demo or os.getenv("FORCE", "").lower() == "true"
    no_send = args.no_send or os.getenv("NO_SEND", "").lower() == "true"

    now = dt.datetime.now(ET)
    if not force and not should_run(now, os.getenv("SCHEDULE", "")):
        return

    cfg = load_config()
    watch: dict[str, str] = cfg["watch"]
    market_syms = [t["symbol"] for t in MARKET_TILES]

    if args.demo:
        quotes = demo_quotes()
    else:
        quotes, session = fetch_quotes(list(dict.fromkeys(market_syms + list(watch))), now.date())
        if session != now.date() and not force:
            print(f"הבורסה סגורה היום (יום המסחר האחרון: {session}) — מדלג")
            return

    mkt = {s: quotes[s] for s in market_syms if s in quotes}
    stocks = [Quote(s, quotes[s].price, quotes[s].prev, g) for s, g in watch.items() if s in quotes]
    if not stocks:
        sys.exit("לא התקבלו נתונים לאף מניה ברשימה")

    n = min(5, len(stocks) // 2 or 1)
    ranked = sorted(stocks, key=lambda s: -s.chg)
    top, bottom = ranked[:n], sorted(ranked[n:], key=lambda s: s.chg)[:n]

    headline, tone = build_headline(stocks)
    spx_chg = mkt["^GSPC"].chg if "^GSPC" in mkt else 0.0
    ups = sum(s.chg > 0 for s in stocks)

    ctx = {
        "brand": cfg.get("brand", "MARKET"), "tagline": cfg.get("tagline", "Daily Market Digest"),
        "stamp": f"{now:%B} {now.day}, {now.year} · {now.strftime('%I:%M %p').lstrip('0')} {now.tzname()}",
        "mood": mood_for(spx_chg), "headline": headline, "tone": tone,
        "story": build_story(stocks, mkt),
        "gainers": {"title": "העולות המובילות" if all(q.chg > 0 for q in top) else "החזקות ברשימה",
                    "rows": stock_rows(top)},
        "losers": {"title": "היורדות המובילות" if all(q.chg < 0 for q in bottom) else "החלשות ברשימה",
                   "rows": stock_rows(bottom)},
        "breadth": f"{ups}/{len(stocks)}",
        "alert": vix_alert(mkt), "tiles": build_tiles(mkt),
        "demo": args.demo,
    }

    OUT_DIR.mkdir(exist_ok=True)
    html = render_html(ctx)
    (OUT_DIR / "last.html").write_text(html, encoding="utf-8")
    png = OUT_DIR / f"market_{now:%Y-%m-%d}.png"
    html_to_png(html, png)
    print(f"🖼️  נשמר: {png}")

    webhook = os.getenv("DISCORD_WEBHOOK_URL", "")
    if no_send or not webhook:
        print("לא נשלח לדיסקורד (אין DISCORD_WEBHOOK_URL או --no-send)")
        return
    plain_title = Markup(headline).striptags()
    send_discord(webhook, png, f"📊 **{plain_title}**")


if __name__ == "__main__":
    main()
