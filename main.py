import time, json, requests
from datetime import datetime, timezone

# ===== مفاتيحك =====
TELEGRAM_TOKEN = "8085180830:AAGHgsKIdVSFNCQ8acDiL8gaulduXauN2xk"
PUBLIC_CHANNEL_ID = "1002608482349"
POLYGON_API = "ht3apHm7nJA2VhvBynMHEcpRI11VSRbq"

# ===== إعدادات عامة =====
SCAN_INTERVAL_SEC = 90          # فحص كل 1.5 دقيقة
PRICE_MIN, PRICE_MAX = 1.0, 10.0
MIN_DAY_VOL = 5_000_000         # حجم تداول يومي أدنى للفلترة
MIN_DAY_CHG = 5.0               # % ارتفاع يومي أدنى
RVOL_SPIKE_FACTOR = 3.5         # سبايك فوليوم لحظي مقابل متوسط 10 شموع
MOMENTUM_N = 3                  # عدد الشموع (3 = 9 دقائق إذا 3m)
MOMENTUM_PCT = 2.0              # ارتفاع 9 دقائق الأدنى
RES_MIN = 3
BACK_MINUTES = 180              # نرجع 3 ساعات

SEEN_FILE = "public_seen.json"  # منع التكرار
COUNT_FILE = "public_counts.json"  # عدد مرات التنبيه اليوم
SUBSCRIBE_URL = "https://t.me/your_payment_or_bot"  # ضع رابط الاشتراك/البوت هنا

# ===== أدوات =====
def _utc_ts(): return int(datetime.now(timezone.utc).timestamp())
def _today_start_ts():
    d = datetime.now(timezone.utc).date()
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())

def _load(path):
    try:
        with open(path, "r") as f: return json.load(f)
    except Exception:
        return {}

def _save(path, data):
    with open(path, "w") as f: json.dump(data, f)

def _poly_get(url, params=None):
    params = dict(params or {})
    params["apiKey"] = POLYGON_API
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json()

def tg_send_with_button(chat_id, text, btn_text="🔑 اشترك الآن", btn_url=SUBSCRIBE_URL):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    keyboard = {"inline_keyboard": [[{"text": btn_text, "url": btn_url}]]}
    requests.post(url, data={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                             "disable_web_page_preview": True},
                  json={"reply_markup": keyboard})

# ===== بيانات Polygon =====
def get_snapshot_gainers():
    data = _poly_get("https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/gainers")
    return data.get("tickers", []) or []

def get_aggs(symbol, frm_ts, to_ts, res=RES_MIN):
    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/{res}/minute/{frm_ts}/{to_ts}"
    data = _poly_get(url, {"adjusted": "true", "limit": 50000})
    return data.get("results", []) or []

# ===== كشف الزخم اللحظي =====
def has_volume_spike(candles, factor=RVOL_SPIKE_FACTOR):
    vols = [c["v"] for c in candles]
    if len(vols) < 12: return False, 0.0, 0
    base = vols[-11:-1]  # آخر 10 قبل الحالية
    base_avg = sum(base)/len(base)
    rvol = vols[-1]/base_avg if base_avg > 0 else 0
    return vols[-1] > base_avg * factor, rvol, vols[-1]

def has_momentum(candles, n=MOMENTUM_N, pct=MOMENTUM_PCT):
    closes = [c["c"] for c in candles]
    if len(closes) < n+1: return False, 0.0
    ref, last = closes[-(n+1)], closes[-1]
    chg = ((last - ref)/ref)*100 if ref > 0 else 0.0
    return chg >= pct, chg

# ===== رسالة القناة العامة =====
def compose_public_msg(t, price, rvolx, last_vol):
    symbol = t.get("ticker")
    day = t.get("day") or {}
    change_pct = t.get("todaysChangePerc") or 0.0
    day_vol = day.get("v") or 0
    marketcap = t.get("marketCap") or 0
    liquidity = price * (day_vol or 0)

    # صياغة مشابهة للصورة + مختصرة وجذابة
    msg = (
        f"🇺🇸 <b>{symbol}</b>\n"
        f"▪️ <b>نوع الحركة:</b> زخم شرائي متوسط 3 دقائق\n"
        f"▪️ <b>نسبة الارتفاع:</b> <b>+{round(change_pct,1)}%</b>\n"
        f"▪️ <b>السعر الحالي:</b> {round(price, 4)} دولار\n"
        f"▪️ <b>الحجم النسبي:</b> {round(rvolx, 1)}X\n"
        f"▪️ <b>حجم آخر شمعة 3م:</b> {int(last_vol):,}\n"
        f"▪️ <b>حجم اليوم:</b> {int(day_vol):,}\n"
        f"▪️ <b>السيولة:</b> ${round(liquidity/1_000_000,2)}M\n"
        f"🕒 <code>{datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC</code>\n\n"
        f"🔑 للدخول والأهداف والوقف — اشترك بالقناة الخاصة"
    )
    return msg

# ===== منطق المسح =====
def process_one(t, seen, counts):
    symbol = t.get("ticker")
    day = t.get("day") or {}
    price = day.get("c") or t.get("lastTrade", {}).get("p")
    change_pct = t.get("todaysChangePerc") or 0.0
    day_vol = day.get("v") or 0

    if not price: return
    if not (PRICE_MIN <= price <= PRICE_MAX): return
    if day_vol < MIN_DAY_VOL: return
    if change_pct < MIN_DAY_CHG: return

    frm = max(_today_start_ts(), _utc_ts() - BACK_MINUTES*60)
    candles = get_aggs(symbol, frm, _utc_ts(), res=RES_MIN)
    if len(candles) < 15: return

    spike, rvolx, last_vol = has_volume_spike(candles)
    momentum_ok, mom_pct = has_momentum(candles)

    if not spike or not momentum_ok:
        return

    # منع تكرار التنبيه لنفس الرمز خلال 30 دقيقة
    last_sent = seen.get(symbol, 0)
    if _utc_ts() - last_sent < 30*60:
        return

    # عدّاد اليوم
    today_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    counts.setdefault(today_key, {})
    counts[today_key][symbol] = counts[today_key].get(symbol, 0) + 1

    # أرسل مع زر الاشتراك
    msg = compose_public_msg(t, price, rvolx, last_vol)
    tg_send_with_button(PUBLIC_CHANNEL_ID, msg)

    seen[symbol] = _utc_ts()
    _save(SEEN_FILE, seen)
    _save(COUNT_FILE, counts)

def run():
    seen = _load(SEEN_FILE)
    counts = _load(COUNT_FILE)

    while True:
        try:
            gainers = get_snapshot_gainers()
            for t in gainers[:80]:       # نكتفي بأول 80 ربحان
                process_one(t, seen, counts)
        except Exception as e:
            # أرسل الخطأ للقناة للتتبّع (اختياري)
            try:
                tg_send_with_button(PUBLIC_CHANNEL_ID, f"⚠️ Bot Error: {e}", "الدعم", "https://t.me/")
            except Exception:
                pass

        time.sleep(SCAN_INTERVAL_SEC)

if __name__ == "__main__":
    run()
