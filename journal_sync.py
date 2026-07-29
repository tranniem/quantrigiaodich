# -*- coding: utf-8 -*-
"""ĐỒNG BỘ LỆNH TAY MT5 → Firebase journal/mt5 (sổ Quản lý lệnh đọc từ đây).

- Đọc LỊCH SỬ LỆNH ĐÃ ĐÓNG từ terminal MT5 đang chạy trên PC (tài khoản nào đăng nhập lấy tài khoản đó).
- CHỈ LỆNH TAY: magic == 0 (lệnh bot có magic riêng, vd 50705 — bỏ qua).
- Ghi Firebase: journal/mt5/<login>_<position_id> — app gộp vào tab Quản lý lệnh, anh Niêm viết đúc kết.
- Chạy: E:\\FTMO-Bot\\.venv312\\Scripts\\python.exe journal_sync.py  (hoặc sync_mt5.bat / Task Scheduler 5')
- Secret Firebase đọc từ E:\\MAXS-Trading\\.env (không nằm trong repo web).
"""
import os
import sys
import json
from datetime import datetime, timedelta

import requests
import MetaTrader5 as mt5

ENV_PATH = r"E:\MAXS-Trading\.env"
FROM_DATE = datetime(2026, 1, 1)          # lấy lịch sử từ đầu 2026


def load_env(path):
    env = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k] = v
    return env


def main():
    env = load_env(ENV_PATH)
    fb, sec = env.get("FIREBASE_URL", "").rstrip("/"), env.get("FIREBASE_SECRET", "")
    if not fb:
        print("Thieu FIREBASE_URL trong .env — dung.")
        return 1
    auth = f"?auth={sec}" if sec else ""

    if not mt5.initialize():
        print("MT5 terminal chua mo — bo qua lan nay.")
        return 0
    ai = mt5.account_info()
    if not ai:
        print("Terminal mo nhung chua dang nhap tai khoan — bo qua.")
        mt5.shutdown()
        return 0

    deals = mt5.history_deals_get(FROM_DATE, datetime.now() + timedelta(days=1)) or []
    mt5_orders = {o.ticket: o for o in (mt5.history_orders_get(FROM_DATE, datetime.now() + timedelta(days=1)) or [])}
    # thong so tung symbol — de TU TINH pip/RR/risk$ cho moi thi truong (FX, vang, chi so, dau...)
    syminfo = {}
    for s in {d.symbol for d in deals if d.symbol}:
        si = mt5.symbol_info(s)
        if si:
            syminfo[s] = {"point": si.point, "digits": si.digits,
                          "tick_size": si.trade_tick_size or si.point,
                          "tick_value": si.trade_tick_value}
    mt5.shutdown()

    # gom deal theo position — chi lenh TAY (magic 0), bo deal so du/nap rut
    pos = {}
    for d in deals:
        if d.type not in (0, 1) or not d.symbol:
            continue
        if d.magic != 0:
            continue                                  # lenh bot — khong vao so tay
        pos.setdefault(d.position_id, []).append(d)

    out, n_open = {}, 0
    for pid, ds in pos.items():
        ins = [d for d in ds if d.entry == 0]
        outs = [d for d in ds if d.entry in (1, 3)]
        if not ins:
            continue
        vin = sum(d.volume for d in ins)
        vout = sum(d.volume for d in outs)
        if vout + 1e-9 < vin:                         # con mo — cho dong roi vao so
            n_open += 1
            continue
        side = "BUY" if ins[0].type == 0 else "SELL"
        entry_px = sum(d.price * d.volume for d in ins) / vin
        close_px = sum(d.price * d.volume for d in outs) / vout if vout else None
        gross = sum(d.profit for d in ds)
        fees = sum(d.commission + d.swap + d.fee for d in ds)
        # SL/TP tot nhat co the biet: tu order da sinh cac deal nay
        sl = tp = 0.0
        for d in ins + outs:
            o = mt5_orders.get(d.order)
            if o:
                sl = o.sl or sl
                tp = o.tp or tp
        # ly do dong (reason cua deal ra): 4 = cham SL, 5 = cham TP
        why = "tay"
        if any(getattr(d, "reason", 0) == 4 for d in outs):
            why = "SL"
        elif any(getattr(d, "reason", 0) == 5 for d in outs):
            why = "TP"
        # === TU TINH pip / RR / risk$ theo thong so symbol (moi thi truong) ===
        si = syminfo.get(ins[0].symbol, {})
        point, digits = si.get("point", 0), si.get("digits", 0)
        pip = point * 10 if digits in (5, 3, 2) else (point or None)   # FX 5/3 so le, vang 2 -> 1 pip = 10 point
        sgn = 1 if side == "BUY" else -1
        pip_sl = round(abs(entry_px - sl) / pip, 1) if (sl and pip) else None
        pip_tp = round(abs(tp - entry_px) / pip, 1) if (tp and pip) else None
        risk_usd = None
        if sl and si.get("tick_size") and si.get("tick_value"):
            risk_usd = round(abs(entry_px - sl) / si["tick_size"] * si["tick_value"] * vin, 2)
        rr_plan = round(abs(tp - entry_px) / abs(entry_px - sl), 2) if (sl and tp and entry_px != sl) else None
        rr_act = None
        if sl and close_px is not None and entry_px != sl:
            rr_act = round((close_px - entry_px) * sgn / abs(entry_px - sl), 2)   # R theo gia
        rr_money = round((gross + fees) / risk_usd, 2) if risk_usd else None      # R theo tien rong (vi that)
        key = f"{ai.login}_{pid}"
        out[key] = {
            "src": "MT5", "acc": ai.login, "server": ai.server,
            "demo": ai.trade_mode != 2,               # 2 = real
            "sym": ins[0].symbol, "side": side, "lot": round(vin, 2),
            "entry": round(entry_px, 5), "close": round(close_px, 5) if close_px else None,
            "sl": sl or None, "tp": tp or None,
            "pipSl": pip_sl, "pipTp": pip_tp, "riskUsd": risk_usd,
            "rrPlan": rr_plan, "rrAct": rr_act, "rrMoney": rr_money, "why": why,
            "openTs": min(d.time_msc for d in ins), "closeTs": max(d.time_msc for d in outs),
            "pnl": round(gross + fees, 2), "gross": round(gross, 2), "fees": round(fees, 2),
            "cmt": (ins[0].comment or "").strip() or None,
        }

    if out:
        r = requests.patch(f"{fb}/journal/mt5.json{auth}", json=out, timeout=15)
        r.raise_for_status()
    meta = {"lastSync": int(datetime.now().timestamp() * 1000), "acc": ai.login, "server": ai.server,
            "demo": ai.trade_mode != 2, "balance": round(ai.balance, 2), "closed": len(out), "open": n_open}
    requests.patch(f"{fb}/journal/mt5meta.json{auth}", json=meta, timeout=15)
    print(f"OK: {len(out)} lenh tay da dong day len Firebase · {n_open} lenh dang mo (cho dong)"
          f" · tai khoan {ai.login} ({'DEMO' if ai.trade_mode != 2 else 'THAT'}) · balance {ai.balance:,.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
