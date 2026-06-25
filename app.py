#!/usr/bin/env python3
"""
Polymarket Copy Trader — Web Interface (Demo + Production)
"""

import os, sys, json, time, threading, logging, traceback
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

load_dotenv()

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# ─────────────────────────────────────────────────────────────
# Persistence helpers
# ─────────────────────────────────────────────────────────────

CONFIG_FILE  = "config.json"
DEMO_FILE    = "demo_state.json"
HISTORY_FILE = "trade_history.json"
LOG_FILE     = "bot.log"

# Lock pour éviter les corruptions de fichiers en écriture concurrente
_file_lock = threading.Lock()

DEFAULT_CONFIG = {
    "wallets_to_track": ["0x63ce342161250d705dc0b16df89036c8e5f9ba9a"],
    "copy_percentage": 1.0,
    "trading_enabled": False,
    "mode": "demo",
    "demo_balance": 1000.0,
    "bet_amount": 10.0,
    "rate_limit": 25
}

DEFAULT_DEMO = {
    "balance": 1000.0,
    "initial_balance": 1000.0,
    "total_pnl": 0.0,
    "total_trades": 0,
    "winning_trades": 0,
    "losing_trades": 0,
    "total_uptime_seconds": 0,
    "positions": []
}

bot_state = {
    "running": False,
    "mode": "demo",
    "start_time": None,
    "thread": None,
    "logs": [],
    "trade_history": [],
    "demo": dict(DEFAULT_DEMO),
    "live_positions": [],
}

def load_json(path, default):
    try:
        with open(path) as f:
            d = json.load(f)
        for k, v in default.items():
            d.setdefault(k, v)
        return d
    except Exception:
        return dict(default)

def save_json(path, data):
    with _file_lock:
        # Écriture atomique : on écrit dans un fichier temporaire puis on renomme
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)

def load_all():
    cfg = load_json(CONFIG_FILE, DEFAULT_CONFIG)
    bot_state["mode"] = cfg.get("mode", "demo")
    demo = load_json(DEMO_FILE, DEFAULT_DEMO)
    bot_state["demo"] = demo
    hist = load_json(HISTORY_FILE, [])
    bot_state["trade_history"] = hist if isinstance(hist, list) else []

load_all()

# ─────────────────────────────────────────────────────────────
# Logger (feeds the /api/logs endpoint)
# ─────────────────────────────────────────────────────────────

class WebHandler(logging.Handler):
    def emit(self, record):
        bot_state["logs"].append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "level": record.levelname,
            "msg": self.format(record)
        })
        if len(bot_state["logs"]) > 500:
            bot_state["logs"] = bot_state["logs"][-500:]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[WebHandler(), logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)
logger = logging.getLogger("CopyTrader")

# ─────────────────────────────────────────────────────────────
# Bot logic
# ─────────────────────────────────────────────────────────────

def bot_loop(config):
    from src.positions import get_user_positions, detect_order_changes
    wallets    = config.get("wallets_to_track", [])
    mode       = config.get("mode", "demo")
    trading_module = None

    if mode == "production" and config.get("trading_enabled"):
        try:
            from src.trading import TradingModule
            trading_module = TradingModule(config)
            logger.info("Connected to Polymarket — Production mode")
        except Exception as e:
            logger.error(f"TradingModule init failed: {e}")

    logger.info(f"Bot started [{mode.upper()}] — {len(wallets)} wallet(s)")

    wallet_states = {}
    for w in wallets:
        pos = get_user_positions(w)
        if pos is not None:
            wallet_states[w] = pos
            bot_state["live_positions"] = pos
            logger.info(f"Initialized {w[:8]}… — {len(pos)} position(s)")

    while bot_state["running"]:
        try:
            for w in wallets:
                cur = get_user_positions(w)
                if cur is None:
                    continue
                bot_state["live_positions"] = cur
                prev = wallet_states.get(w, [])
                changes = detect_order_changes(prev, cur)
                for ch in changes:
                    logger.info(f"Detected {ch['type']} — {ch.get('title','?')} — {ch['size']:.2f}")
                    handle_change(ch, config, trading_module, mode)
                wallet_states[w] = cur
        except Exception as e:
            logger.error(f"Loop error: {e}")
        time.sleep(2)

    logger.info("Bot stopped.")

def handle_change(change, config, trading_module, mode):
    rec = {
        "time":    datetime.now().isoformat(),
        "type":    change["type"],
        "title":   change.get("title", "Unknown"),
        "outcome": change.get("outcome", ""),
        "size":    float(change["size"]),
        "price":   float(change.get("price") or 0),
        "mode":    mode,
        "status":  "dry-run",
        "pnl":     None
    }

    if mode == "demo":
        demo = bot_state["demo"]
        bet  = float(config.get("bet_amount", 10.0))

        if change["type"] == "BUY":
            if demo["balance"] >= bet:
                demo["balance"] -= bet
                demo["positions"].append({
                    "asset":    change["asset"],
                    "title":    change.get("title",""),
                    "outcome":  change.get("outcome",""),
                    "size":     float(change["size"]),
                    "avgPrice": float(change.get("price") or 0.5),
                    "cost":     bet
                })
                demo["total_trades"] += 1
                rec["status"] = "demo-buy"
                rec["amount"] = bet
                logger.info(f"[DEMO BUY] -{bet:.2f} USDC → balance {demo['balance']:.2f}")
            else:
                rec["status"] = "demo-skipped"
                logger.warning(f"[DEMO] Insufficient balance {demo['balance']:.2f} < {bet:.2f}")

        elif change["type"] == "SELL":
            pos = next((p for p in demo["positions"] if p["asset"] == change["asset"]), None)
            if pos:
                sell_price = float(change.get("price") or pos["avgPrice"])
                pnl = (sell_price - pos["avgPrice"]) * pos["size"]
                demo["balance"]    += pos["cost"] + pnl
                demo["total_pnl"]  += pnl
                if pnl >= 0: demo["winning_trades"] += 1
                else:        demo["losing_trades"]  += 1
                demo["positions"] = [p for p in demo["positions"] if p["asset"] != change["asset"]]
                demo["total_trades"] += 1
                rec.update({"status": "demo-sell", "pnl": round(pnl, 4)})
                logger.info(f"[DEMO SELL] PnL {pnl:+.4f} → balance {demo['balance']:.2f}")

        save_json(DEMO_FILE, demo)

    elif mode == "production":
        if trading_module and config.get("trading_enabled"):
            try:
                order = trading_module.execute_copy_trade(change)
                rec["status"] = "executed"
                if order:
                    rec["order_id"] = str(getattr(order, "order_id", ""))
                logger.info(f"[PROD] Executed {change['type']} {change.get('title')}")
            except Exception as e:
                rec["status"] = "error"
                rec["error"]  = str(e)
                logger.error(f"[PROD] Order failed: {e}")
        else:
            logger.info(f"[PROD DRY-RUN] Would {change['type']} {change['size']:.2f} of {change.get('title')}")

    bot_state["trade_history"].append(rec)
    if len(bot_state["trade_history"]) > 1000:
        bot_state["trade_history"] = bot_state["trade_history"][-1000:]
    save_json(HISTORY_FILE, bot_state["trade_history"])

# ─────────────────────────────────────────────────────────────
# Flask app
# ─────────────────────────────────────────────────────────────

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/status")
def api_status():
    # Détection de crash silencieux du thread
    if bot_state["running"]:
        t = bot_state.get("thread")
        if t and not t.is_alive():
            logger.error("Bot thread crashed silently, resetting state")
            bot_state["running"] = False
            if bot_state["start_time"]:
                elapsed = int((datetime.now() - bot_state["start_time"]).total_seconds())
                bot_state["demo"]["total_uptime_seconds"] = bot_state["demo"].get("total_uptime_seconds", 0) + elapsed
                save_json(DEMO_FILE, bot_state["demo"])
                bot_state["start_time"] = None
    
    uptime = 0
    if bot_state["start_time"]:
        uptime = int((datetime.now() - bot_state["start_time"]).total_seconds())
    demo   = bot_state["demo"]
    closed = demo["winning_trades"] + demo["losing_trades"]
    win_rate = round(demo["winning_trades"] / closed * 100, 1) if closed else 0
    cfg    = load_json(CONFIG_FILE, DEFAULT_CONFIG)

    return jsonify({
        "running":               bot_state["running"],
        "mode":                  bot_state["mode"],
        "uptime_seconds":        uptime,
        "total_uptime_seconds":  demo.get("total_uptime_seconds", 0) + uptime,
        "wallets":               cfg.get("wallets_to_track", []),
        "copy_percentage":       cfg.get("copy_percentage", 1.0),
        "bet_amount":            cfg.get("bet_amount", 10.0),
        "trading_enabled":       cfg.get("trading_enabled", False),
        "live_positions_count":  len(bot_state["live_positions"]),
        "demo": {
            "balance":         round(demo["balance"], 2),
            "initial_balance": round(demo["initial_balance"], 2),
            "total_pnl":       round(demo["total_pnl"], 4),
            "total_trades":    demo["total_trades"],
            "win_rate":        win_rate,
            "open_positions":  len(demo.get("positions", [])),
        }
    })

@app.route("/api/start", methods=["POST"])
def api_start():
    if bot_state["running"]:
        # Vérifie si le thread est encore vivant (crash silencieux)
        t = bot_state.get("thread")
        if t and not t.is_alive():
            bot_state["running"] = False
            logger.warning("Bot thread was dead, resetting state.")
        else:
            return jsonify({"ok": False, "msg": "Already running"})
    cfg = load_json(CONFIG_FILE, DEFAULT_CONFIG)
    if not cfg.get("wallets_to_track"):
        return jsonify({"ok": False, "msg": "No wallet configured"})
    bot_state.update(running=True, start_time=datetime.now(), mode=cfg.get("mode","demo"))
    t = threading.Thread(target=bot_loop, args=(cfg,), daemon=True)
    bot_state["thread"] = t
    t.start()
    logger.info(f"Bot started — {bot_state['mode'].upper()}")
    return jsonify({"ok": True})

@app.route("/api/stop", methods=["POST"])
def api_stop():
    if not bot_state["running"]:
        return jsonify({"ok": False, "msg": "Not running"})
    bot_state["running"] = False
    if bot_state["start_time"]:
        elapsed = int((datetime.now() - bot_state["start_time"]).total_seconds())
        bot_state["demo"]["total_uptime_seconds"] = bot_state["demo"].get("total_uptime_seconds", 0) + elapsed
        save_json(DEMO_FILE, bot_state["demo"])
        bot_state["start_time"] = None
    logger.info("Bot stopped by user")
    return jsonify({"ok": True})

@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    if request.method == "GET":
        return jsonify(load_json(CONFIG_FILE, DEFAULT_CONFIG))
    data = request.json or {}
    cfg  = load_json(CONFIG_FILE, DEFAULT_CONFIG)
    for field in ["wallets_to_track","copy_percentage","trading_enabled","mode","demo_balance","bet_amount","rate_limit"]:
        if field in data:
            cfg[field] = data[field]
    if "demo_balance" in data and not bot_state["running"]:
        nb = float(data["demo_balance"])
        bot_state["demo"]["balance"]         = nb
        bot_state["demo"]["initial_balance"] = nb
        save_json(DEMO_FILE, bot_state["demo"])
    save_json(CONFIG_FILE, cfg)
    bot_state["mode"] = cfg.get("mode","demo")
    logger.info(f"Config updated — mode:{cfg['mode']} wallet:{cfg['wallets_to_track']}")
    return jsonify({"ok": True})

@app.route("/api/positions")
def api_positions():
    return jsonify(bot_state["live_positions"])

@app.route("/api/demo/positions")
def api_demo_positions():
    return jsonify(bot_state["demo"].get("positions", []))

@app.route("/api/demo/reset", methods=["POST"])
def api_demo_reset():
    if bot_state["running"]:
        return jsonify({"ok": False, "msg": "Stop the bot first"})
    cfg = load_json(CONFIG_FILE, DEFAULT_CONFIG)
    bal = float(cfg.get("demo_balance", 1000.0))
    nd  = dict(DEFAULT_DEMO)
    nd["balance"] = nd["initial_balance"] = bal
    bot_state["demo"] = nd
    save_json(DEMO_FILE, nd)
    logger.info(f"Demo reset — balance: {bal}")
    return jsonify({"ok": True})

@app.route("/api/trades")
def api_trades():
    limit = int(request.args.get("limit", 100))
    return jsonify(bot_state["trade_history"][-limit:])

@app.route("/api/logs")
def api_logs():
    limit = int(request.args.get("limit", 150))
    return jsonify(bot_state["logs"][-limit:])

if __name__ == "__main__":
    load_all()
    print("\n🚀  Polymarket Copy Trader  →  http://localhost:5051\n")
    app.run(host="0.0.0.0", port=5051, debug=False)
