# main.py
# -*- coding: utf-8 -*-
"""
Finviz -> Finnhub -> Telegram Signals
- Uses FINVIZ_URL to get candidate symbols
- Uses FINNHUB_API_KEY to fetch 3-min candles and compute VWAP + resistance
- Entry: breakout resistance OR price >= VWAP
- Stop: VWAP (lower) minus small buffer
- Targets: +7%, +15%, +25%, +40%
- Sends TOP_LIMIT signals per run (default 3)
- Scheduler: runs at 16:35 Asia/Riyadh then repeats every 30 minutes until 23:00
"""

import os
import time
import math
import logging
import requests
from datetime import datetime, timedelta
import pandas as pd
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from pytz import timezone as tz

# ---------------- CONFIG ----------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # e.g. -1002608482349
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
# default to your provided finviz filter if env not set (you can remove default to force env usage)
FINVIZ_URL = os.getenv("FINVIZ_URL", "https://finviz.com/screener.ashx?v=111&f=sh_curvol_o500%2Csh_float_u20%2Csh_price_1to10%2Cta_changeopen_u10%2Cta_perf_10to-i10&ft=4")
TOP_LIMIT = int(os.getenv("TOP_LIMIT", "3"))
TIMEZONE = os.getenv("TIMEZONE", "Asia/Riyadh")

# Finnhub / candles
FINNHUB_BASE = "https://finnhub.io/api/v1"
RES_MIN = 3                # 3-minute candles
VWAP_LOOKBACK_MIN = 120    # last 120 minutes (2 hours)

# market window (Saudi times)
MARKET_CLOSE_HOUR = 23  # 23:00 Riyadh (adjust if needed)

# logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

# -------------- helpers -----------------
def send_telegram(text: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error("TELEGRAM_TOKEN or TELEGRAM_CHAT_ID not set in environment.")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }, timeout=15)
        if r.status_code != 200:
            logging.error("Telegram send error: %s", r.text)
            return False
        return True
    except Exception:
        logging.exception("send_telegram failed")
        return False

def fmt(x, nd=4):
    try:
        return f"{float(x):.{nd}f}"
    except:
        return str(x)

def tick_for_price(p: float) -> float:
    """small tick buffer depending on price"""
    if p < 3.0:
        return 0.01
    if p < 6.0:
        return 0.02
    return 0.03

# ------------- Finviz scraping -----------
def get_symbols_from_finviz(url: str):
    logging.info("Fetching Finviz filter: %s", url)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    r = requests.get(url, headers=headers, timeout=25)
    r.raise_for_status()
    tables = pd.read_html(r.text)
    for tb in tables:
        cols = [str(c).strip().lower() for c in tb.columns]
        if "ticker" in cols or "symbol" in cols:
            col = tb.columns[cols.index("ticker")] if "ticker" in cols else tb.columns[cols.index("symbol")]
            syms = tb[col].dropna().astype(str).str.strip().tolist()
            # simple cleanup
            syms = [s for s in syms if s.replace("-", "").isalnum()]
            logging.info("Found %d symbols in Finviz table", len(syms))
            return syms
    logging.info("No Finviz symbol table found.")
    return []

# ------------- Finnhub candles & VWAP ----------
def finnhub_candles(symbol: str, minutes: int = VWAP_LOOKBACK_MIN, res_min: int = RES_MIN):
    end = int(time.time())
    start = end - minutes * 60
    params = {"symbol": symbol, "resolution": res_min, "from": start, "to": end, "token": FINNHUB_API_KEY}
    url = f"{FINNHUB_BASE}/stock/candle"
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    if data.get("s") != "ok":
        return pd.DataFrame()
    return pd.DataFrame({
        "t": data.get("t", []),
        "o": data.get("o", []),
        "h": data.get("h", []),
        "l": data.get("l", []),
        "c": data.get("c", []),
        "v": data.get("v", []),
    })

def compute_vwap(df: pd.DataFrame) -> float or None:
    if df.empty or not {'h','l','c','v'}.issubset(df.columns):
        return None
    tp = (df['h'] + df['l'] + df['c']) / 3.0
    vol = df['v'].clip(lower=0.0)
    denom = vol.sum()
    if denom <= 0:
        return None
    return float((tp * vol).sum() / denom)

# ------------- resistance detection -----------
def find_nearest_resistance(df: pd.DataFrame, lookback: int = 50) -> float or None:
    """
    Find repeated highs in last `lookback` candles.
    Consider levels repeated at least twice as resistance candidates.
    Return the nearest candidate above current price if any,
    else highest candidate available (fallback).
    """
    if df.empty or 'h' not in df.columns:
        return None
    highs = df['h'].tail(lookback).round(2).tolist()
    freq = {}
    for h in highs:
        freq[h] = freq.get(h, 0) + 1
    candidates = sorted([lvl for lvl,count in freq.items() if count >= 2])
    if not candidates:
        return None
    current = float(df['c'].iloc[-1])
    above = [x for x in candidates if x > current]
    if above:
        return above[0]
    return candidates[-1]

# ------------- decision logic --------------
def decide_entry(symbol: str):
    """
    Returns dict with signal info or None if no entry.
    Entry when: breakout resistance OR last_close >= vwap
    Stop = VWAP - tick
    Targets = entry * (1 + pct)
    """
    try:
        df = finnhub_candles(symbol)
    except Exception:
        logging.exception("Failed fetching candles for %s", symbol)
        return None

    if df.empty:
        return None

    # compute VWAP
    vwap = compute_vwap(df)
    if not vwap:
        return None

    last_close = float(df['c'].iloc[-1])
    res = find_nearest_resistance(df, lookback=50)
    tick = tick_for_price(last_close)

    entry = None
    reason = None

    # breakout condition: last_close > res and last_close >= vwap
    if res is not None and last_close > res and last_close >= vwap:
        # use resistance+tick (or last_close if higher)
        entry_val = max(res + tick, last_close)
        entry = round(entry_val, 4)
        reason = f"breakout_res {res}"
    elif last_close >= vwap:
        entry_val = vwap + tick
        entry = round(entry_val, 4)
        reason = "above_vwap"
    else:
        return None

    # stop = VWAP lower minus small buffer
    stop = max(0.0, round(vwap - tick, 4))

    # targets as percentages (7%,15%,25%,40%)
    targets_perc = [0.07, 0.15, 0.25, 0.40]
    targets = [round(entry * (1 + p), 4) for p in targets_perc]

    # sanity: require reasonable spread (optional) - skip here

    return {
        "symbol": symbol,
        "entry": entry,
        "stop": stop,
        "targets": targets,
        "vwap": round(vwap, 4),
        "resistance": res,
        "last_close": round(last_close, 4),
        "reason": reason
    }

# ------------- main job -------------
SEEN = set()  # to prevent duplicates same day
def job_run():
    logging.info("Job started: fetching Finviz and analyzing candidates...")
    date_key = datetime.now(tz(TIMEZONE)).strftime("%Y-%m-%d")
    global SEEN

    # reset SEEN daily
    SEEN = {k for k in SEEN if not k.startswith(date_key)} if SEEN else set()

    # 1) fetch symbols from finviz
    try:
        symbols = get_symbols_from_finviz(FINVIZ_URL)
    except Exception:
        logging.exception("Failed to read Finviz URL")
        send_telegram("⚠️ خطأ: تعذّر قراءة فلتر Finviz.")
        return

    if not symbols:
        logging.info("No symbols returned from Finviz.")
        send_telegram("نتيجة: لا توجد أسهم في فلترك الآن.")
        return

    signals = []
    for s in symbols:
        if len(signals) >= TOP_LIMIT:
            break
        key = f"{date_key}:{s}"
        if key in SEEN:
            continue
        # attempt decision
        try:
            sig = decide_entry(s)
            # small delay to avoid hitting rate limits
            time.sleep(0.6)
            if sig:
                signals.append(sig)
                SEEN.add(key)
        except Exception:
            logging.exception("Error processing %s", s)
            continue

    if not signals:
        send_telegram("لا توجد فرص تستوفي شروط الدخول الآن.")
        logging.info("No valid signals found this run.")
        return

    # send each as separate message
    for sig in signals:
        lines = [
            f"<b>{sig['symbol']}</b>",
            f"دخول {fmt(sig['entry'], nd=4)}",
            f"الهدف 1: {fmt(sig['targets'][0], nd=4)} (7%)",
            f"الهدف 2: {fmt(sig['targets'][1], nd=4)} (15%)",
            f"الهدف 3: {fmt(sig['targets'][2], nd=4)} (25%)",
            f"الهدف 4: {fmt(sig['targets'][3], nd=4)} (40%)",
            f"وقف {fmt(sig['stop'], nd=4)}",
            f"سبب: {sig.get('reason','')}",
        ]
        text = "\n".join(lines)
        send_telegram(text)
        time.sleep(1.0)

    logging.info("Job finished: sent %d signals", len(signals))

# ------------- scheduler --------------
def start_scheduler():
    scheduler = BackgroundScheduler(timezone=tz(TIMEZONE))

    # Cron at 16:35 local time (first run)
    scheduler.add_job(job_run, CronTrigger(hour=16, minute=35, timezone=tz(TIMEZONE)))

    # Interval: every 30 minutes starting at 16:35 until today's MARKET_CLOSE_HOUR
    # compute today's start and end in timezone-aware strings
    today = datetime.now(tz(TIMEZONE)).date()
    start_dt = tz(TIMEZONE).localize(datetime.combine(today, datetime.min.time()).replace(hour=16, minute=35))
    end_dt = tz(TIMEZONE).localize(datetime.combine(today, datetime.min.time()).replace(hour=MARKET_CLOSE_HOUR, minute=0))

    # Add interval job that starts at 16:35 and repeats every 30 minutes until end_dt
    scheduler.add_job(job_run, IntervalTrigger(minutes=30, start_date=start_dt, end_date=end_dt, timezone=tz(TIMEZONE)))

    scheduler.start()
    logging.info("Scheduler started: first run at 16:35 and every 30 minutes until %02d:00 %s", MARKET_CLOSE_HOUR, TIMEZONE)

if __name__ == "__main__":
    # basic checks
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error("Set TELEGRAM_TOKEN and TELEGRAM_CHAT_ID in environment before running.")
        raise SystemExit("Missing TELEGRAM_TOKEN or TELEGRAM_CHAT_ID")
    if not FINNHUB_API_KEY:
        logging.error("Set FINNHUB_API_KEY in environment before running.")
        raise SystemExit("Missing FINNHUB_API_KEY")
    if not FINVIZ_URL:
        logging.error("Set FINVIZ_URL in environment before running.")
        raise SystemExit("Missing FINVIZ_URL")

    # Test startup notification
    send_telegram("✅ بوت التوصيات شغّال — سيبدأ العمل 16:35 Asia/Riyadh (TOP_LIMIT=%d)" % TOP_LIMIT)

    start_scheduler()
    try:
        # keep alive
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logging.info("Stopped by user.")
