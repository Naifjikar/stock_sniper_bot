import os
import time
import json
import math
import requests
from datetime import datetime, timedelta, timezone

# =========================
# ENV CONFIG
# =========================
TG_TOKEN     = os.getenv("TG_TOKEN", "").strip()
CHAT_ID      = os.getenv("CHAT_ID", "").strip()  # قناة/جروب (مثال: -100xxxxxxxxxx)
FINNHUB_KEY  = os.getenv("FINNHUB_KEY", "").strip()

# Watchlist (لازم)
# مثال:
# WATCHLIST=SOUN,BNZI,INTZ,HOLO,MULN,TSLA,NVDA,COIN,PLTR
WATCHLIST = [s.strip().upper() for s in os.getenv("WATCHLIST", "").split(",") if s.strip()]

# شروط الزخم
PRICE_MIN = float(os.getenv("PRICE_MIN", "1"))
PRICE_MAX = float(os.getenv("PRICE_MAX", "10"))

MIN_CHANGE_FROM_PREV_CLOSE = float(os.getenv("MIN_CHANGE_PCT", "8"))   # +8%
MIN_5M_MOVE_PCT            = float(os.getenv("MIN_5M_MOVE_PCT", "3"))  # +3%

MIN_DAY_VOL = int(os.getenv("MIN_DAY_VOL", "1000000"))                # 1,000,000
VOL_SPIKE_MULT = float(os.getenv("VOL_SPIKE_MULT", "3"))              # 3x

MAX_PICKS_PER_DAY = int(os.getenv("MAX_PICKS", "5"))

# أهداف/وقف
STOP_PCT = float(os.getenv("STOP_PCT", "9"))  # -9%
T1 = float(os.getenv("T1", "8"))
T2 = float(os.getenv("T2", "15"))
T3 = float(os.getenv("T3", "25"))
T4 = float(os.getenv("T4", "40"))

# التشغيل
SCAN_EVERY_SECONDS = int(os.getenv("SCAN_EVERY_SECONDS", "120"))  # كل دقيقتين
STATE_FILE = os.getenv("STATE_FILE", "state.json")

# توقيت السعودية
KSA = timezone(timedelta(hours=3))

# =========================
# BASIC VALIDATION
# =========================
def _require(name, val):
    if not val:
        raise RuntimeError(f"Missing ENV var: {name}")

_require("TG_TOKEN", TG_TOKEN)
_require("CHAT_ID", CHAT_ID)
_require("FINNHUB_KEY", FINNHUB_KEY)
if not WATCHLIST:
    raise RuntimeError("WATCHLIST is empty. Put symbols in ENV WATCHLIST=AAA,BBB,...")

# =========================
# TELEGRAM
# =========================
def tg_send(text: str):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    r = requests.post(
        url,
        json={"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True},
        timeout=20
    )
    if r.status_code != 200:
        raise RuntimeError(f"Telegram error {r.status_code}: {r.text}")

# =========================
# STATE
# =========================
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "day": "",             # YYYY-MM-DD (KSA)
        "sent": {},            # symbol -> YYYY-MM-DD
        "active": {},          # symbol -> {entry, entry_ts, high_since_entry}
    }

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def today_ksa_str():
    return datetime.now(KSA).strftime("%Y-%m-%d")

# =========================
# FINNHUB HELPERS
# =========================
def finnhub_quote(symbol: str):
    url = "https://finnhub.io/api/v1/quote"
    r = requests.get(url, params={"symbol": symbol, "token": FINNHUB_KEY}, timeout=20)
    r.raise_for_status()
    return r.json()  # c,o,h,l,pc,t

def finnhub_candles(symbol: str, resolution: str, _from: int, _to: int):
    # resolution: "1", "5", "15", ...
    url = "https://finnhub.io/api/v1/stock/candle"
    r = requests.get(
        url,
        params={"symbol": symbol, "resolution": resolution, "from": _from, "to": _to, "token": FINNHUB_KEY},
        timeout=20
    )
    r.raise_for_status()
    data = r.json()
    # data: {"c":[...], "h":[...], "l":[...], "o":[...], "t":[...], "v":[...], "s":"ok"}
    return data

def calc_vwap(ohlc):
    # VWAP من الشموع: sum((H+L+C)/3 * V) / sum(V)
    c = ohlc.get("c", [])
    h = ohlc.get("h", [])
    l = ohlc.get("l", [])
    v = ohlc.get("v", [])
    if not c or not v or len(c) != len(v):
        return None
    num = 0.0
    den = 0.0
    for i in range(len(c)):
        tp = (h[i] + l[i] + c[i]) / 3.0
        vol = v[i]
        num += tp * vol
        den += vol
    if den <= 0:
        return None
    return num / den

# =========================
# MOMENTUM LOGIC
# =========================
def is_momentum_early(symbol: str):
    """
    يرجع (ok, info_dict) بناء على:
    - سعر 1-10
    - % تغيير من إغلاق أمس >= 8% OR حركة آخر 5 دقائق >= 3%
    - فوليوم اليوم >= 1M OR فوليوم آخر 5 دقائق >= 3x متوسط 5 دقائق
    - اختراق High آخر 5 دقائق (على شموع 1 دقيقة) + فوق VWAP
    """
    q = finnhub_quote(symbol)
    price = float(q.get("c") or 0)
    prev_close = float(q.get("pc") or 0)

    if price <= 0 or prev_close <= 0:
        return False, {}

    if not (PRICE_MIN <= price <= PRICE_MAX):
        return False, {}

    change_pct = ((price - prev_close) / prev_close) * 100.0

    now = datetime.now(timezone.utc)
    to_ts = int(now.timestamp())
    from_ts = int((now - timedelta(minutes=90)).timestamp())

    # شموع 1 دقيقة لآخر 90 دقيقة
    candles_1m = finnhub_candles(symbol, "1", from_ts, to_ts)
    if candles_1m.get("s") != "ok":
        return False, {}

    c = candles_1m["c"]
    h = candles_1m["h"]
    t = candles_1m["t"]
    v = candles_1m["v"]

    if len(c) < 15:
        return False, {}

    # حركة آخر 5 دقائق تقريبًا: آخر إغلاق - إغلاق قبل 5 شموع
    last = c[-1]
    prev_5 = c[-6] if len(c) >= 6 else c[0]
    move_5m_pct = ((last - prev_5) / prev_5) * 100.0 if prev_5 > 0 else 0.0

    momentum_ok = (change_pct >= MIN_CHANGE_FROM_PREV_CLOSE) or (move_5m_pct >= MIN_5M_MOVE_PCT)
    if not momentum_ok:
        return False, {}

    # فوليوم اليوم من الشموع المتاحة (مو دايم يغطي كامل اليوم، لكن يعطي إشارة قوية)
    day_vol_est = int(sum(v))

    # سبايك فوليوم: آخر 5 شموع حجمها مقارنة بمتوسط 5 شموع قبلها
    last5_vol = sum(v[-5:])
    prev_blocks = v[-30:-5] if len(v) >= 30 else v[:-5]
    avg5 = (sum(prev_blocks) / len(prev_blocks)) if prev_blocks else 0
    vol_spike_ok = (day_vol_est >= MIN_DAY_VOL) or (avg5 > 0 and last5_vol >= (VOL_SPIKE_MULT * avg5))

    if not vol_spike_ok:
        return False, {}

    # اختراق High آخر 5 دقائق (نأخذ أعلى High لآخر 5 شموع قبل الأخيرة)
    prev5_high = max(h[-6:-1]) if len(h) >= 6 else max(h[:-1])
    breakout_ok = price > prev5_high

    if not breakout_ok:
        return False, {}

    # VWAP
    vwap = calc_vwap(candles_1m)
    if vwap is None:
        return False, {}

    vwap_ok = price > vwap
    if not vwap_ok:
        return False, {}

    info = {
        "price": round(price, 2),
        "change_pct": round(change_pct, 2),
        "move_5m_pct": round(move_5m_pct, 2),
        "vwap": round(vwap, 2),
        "prev5_high": round(prev5_high, 2),
        "day_vol_est": day_vol_est
    }
    return True, info

def format_signal(symbol: str, entry: float):
    stop = round(entry * (1.0 - STOP_PCT/100.0), 2)
    t1 = round(entry * (1.0 + T1/100.0), 2)
    t2 = round(entry * (1.0 + T2/100.0), 2)
    t3 = round(entry * (1.0 + T3/100.0), 2)
    t4 = round(entry * (1.0 + T4/100.0), 2)

    msg = (
        f"{symbol}\n"
        f"دخول: {entry}\n"
        f"وقف: {stop}\n"
        f"الأهداف:\n"
        f"{t1} - {t2} - {t3} - {t4}"
    )
    return msg

# =========================
# RESULTS (HIGH SINCE ENTRY)
# =========================
def update_highs(state):
    # يحدّث أعلى سعر وصل له السهم منذ الدخول
    for sym, info in list(state["active"].items()):
        entry_ts = int(info.get("entry_ts", 0))
        if entry_ts <= 0:
            continue

        now = datetime.now(timezone.utc)
        to_ts = int(now.timestamp())
        from_ts = max(entry_ts - 60, to_ts - 60*60*8)  # لا يطلب فترة ضخمة مرة

        try:
            candles = finnhub_candles(sym, "1", from_ts, to_ts)
            if candles.get("s") != "ok":
                continue
            highs = candles.get("h", [])
            if not highs:
                continue
            high_since = max(highs)
            if high_since > float(info.get("high_since_entry", 0)):
                info["high_since_entry"] = round(high_since, 2)
                state["active"][sym] = info
        except Exception as e:
            print("update_highs error:", sym, e)

def send_midnight_results_and_reset(state):
    # يرسل النتائج 12:00 الليل (KSA) ثم يصفّر اليوم
    if not state["active"]:
        tg_send("نتائج اليوم:\nلا توجد فرص اليوم.")
        state["active"] = {}
        state["sent"] = {}
        state["day"] = today_ksa_str()
        save_state(state)
        return

    lines = ["نتائج اليوم (أعلى سعر من نقطة الدخول):"]
    for sym, info in state["active"].items():
        entry = float(info["entry"])
        highp = float(info.get("high_since_entry", entry))
        pct = ((highp - entry) / entry) * 100.0 if entry > 0 else 0.0
        lines.append(
            f"{sym}\n"
            f"دخول: {entry}\n"
            f"أعلى سعر: {round(highp,2)}\n"
            f"النسبة: {round(pct,2)}%"
        )

    tg_send("\n\n".join(lines))

    # Reset day
    state["active"] = {}
    state["sent"] = {}
    state["day"] = today_ksa_str()
    save_state(state)

# =========================
# CORE RUN
# =========================
def run_scan(state):
    day = today_ksa_str()
    if state.get("day") != day:
        # يوم جديد
        state["day"] = day
        state["sent"] = {}
        state["active"] = {}
        save_state(state)

    picked_today = [s for s, d in state["sent"].items() if d == day]
    remaining = max(0, MAX_PICKS_PER_DAY - len(picked_today))
    if remaining <= 0:
        return

    for sym in WATCHLIST:
        if remaining <= 0:
            break

        # منع التكرار
        if state["sent"].get(sym) == day:
            continue

        try:
            ok, info = is_momentum_early(sym)
            if not ok:
                continue

            entry = info["price"]  # دخول = السعر الحالي وقت تحقق الشروط
            tg_send(format_signal(sym, entry))

            # حفظ
            state["sent"][sym] = day
            state["active"][sym] = {
                "entry": entry,
                "entry_ts": int(datetime.now(timezone.utc).timestamp()),
                "high_since_entry": entry
            }
            save_state(state)

            remaining -= 1
            time.sleep(1.5)

        except Exception as e:
            print("scan error:", sym, e)
            time.sleep(1.0)

# =========================
# MAIN LOOP (Render friendly)
# =========================
def main():
    state = load_state()
    print("🚀 Momentum bot started and running...")

    last_midnight_sent = ""  # YYYY-MM-DD (KSA) لتجنب تكرار الإرسال

    while True:
        try:
            now_ksa = datetime.now(KSA)
            day = now_ksa.strftime("%Y-%m-%d")

            # تحديث أعلى سعر للأسهم المفعلة
            update_highs(state)

            # إرسال النتائج عند 12:00 الليل (00:00)
            # نخلي نافذة 2 دقائق لتجاوز التأخير
            if now_ksa.hour == 0 and now_ksa.minute in (0, 1) and last_midnight_sent != day:
                send_midnight_results_and_reset(state)
                last_midnight_sent = day

            # سكان الزخم وإرسال 5 فرص فقط باليوم
            run_scan(state)

            time.sleep(SCAN_EVERY_SECONDS)

        except Exception as e:
            print("FATAL LOOP ERROR:", e)
            time.sleep(10)

if __name__ == "__main__":
    main()
