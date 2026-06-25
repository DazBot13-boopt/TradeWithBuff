# Polymarket Copy Trader — Pro Web Dashboard

A copy-trading bot for Polymarket with a full-featured web interface. Supports **Demo mode** (virtual wallet) and **Production mode** (real trades).

---

## Features

- **Demo Mode** — Virtual wallet with configurable starting balance and bet size, P&L tracking, win rate, and uptime stats
- **Production Mode** — Real trading via Polymarket API (requires private key)
- **Live Dashboard** — Animated ticker, stats cards, P&L chart, recent trades
- **Positions** — Live tracked wallet + virtual demo positions
- **Trade History** — Filterable history with P&L per trade
- **Settings** — Change wallet, copy %, bet size, and mode without restarting
- **Live Logs** — Real-time bot logs in browser

---

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure environment (for Production only)
```bash
cp .env.example .env
# Edit .env with your keys:
# POLYMARKET_PRIVATE_KEY=your_private_key_here
# POLYMARKET_PROXY_ADDRESS=your_proxy_address
```

### 3. Run
```bash
python app.py
```

Open → **http://localhost:5000**

---

## Modes

| | Demo | Production |
|---|---|---|
| Real money | ❌ | ✅ |
| Virtual wallet | ✅ | ❌ |
| P&L tracking | ✅ (simulated) | ✅ (real) |
| API keys needed | ❌ | ✅ |

---

## Config

All settings are available in the **Settings** tab of the UI:

| Field | Description |
|---|---|
| Wallet to Copy | The Polymarket wallet address to track |
| Copy Percentage | % of the tracked trader's position size to copy |
| Bet Amount | Fixed USDC amount per trade in Demo mode |
| Starting Balance | Virtual starting balance for Demo mode |
| Enable Real Trading | Toggle live trade execution |

---

## File Structure

```
├── app.py              # Flask server + bot logic
├── config.json         # Bot configuration (auto-updated by UI)
├── demo_state.json     # Demo wallet state (auto-generated)
├── trade_history.json  # Trade history (auto-generated)
├── bot.log             # Log file (auto-generated)
├── src/
│   ├── main.py         # Original CLI entry point
│   ├── positions.py    # Polymarket position fetching
│   └── trading.py      # Order execution
└── templates/
    └── index.html      # Web dashboard
```
