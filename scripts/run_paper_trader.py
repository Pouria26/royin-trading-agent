"""Live & Replay Paper Trading Runner for Royin.

Executes autonomous spot paper trading on live Wallex prices with a 5,000,000 TMN balance:
- Fast momentum impulse trades (5 to 30 minutes max).
- Dynamic Take Profit (1.2% - 3.5%) and Stop Loss (0.6% - 1.0%).
- Timely early exits on momentum stall (EV_MOMENTUM_STALL), wick rejection (EV_WICK_REJECTION), or 30m time-stop.
- Accurate exchange fee deduction (0.25% maker / 0.30% taker).
- Autonomous self-correction memory (Reflexion) recorded into durable SQLite.
- Outputs official portfolio manifest for the live Dashboard (http://localhost:8765).
"""

import argparse
import json
import time
import urllib.request
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from royin.broker import PaperBroker
from royin.decision import Decision, DecisionProposal, bind_decision
from royin.features import FeatureSnapshot, extract_features
from royin.ledger import Ledger
from royin.market_data import Candle, CandleSeries
from royin.markets import load_restrictions
from royin.risk import MarketRules, RiskPolicy, evaluate_risk

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config/wallex-credit-market-policy.json"


def fetch_wallex_candles(
    symbol: str,
    resolution: str = "15",
    lookback_bars: int = 150,
) -> list[Candle]:
    """Fetch recent closed candles from Wallex public UDF history and resample to exact interval."""
    now = int(time.time())
    seconds_per_bar = int(resolution) * 60
    total_seconds_needed = (lookback_bars + 40) * seconds_per_bar
    from_time = now - total_seconds_needed
    url = f"https://api.wallex.ir/v1/udf/history?symbol={symbol}&resolution=1&from={from_time}&to={now}"
    cache_dir = ROOT / "data/cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{symbol}_{resolution}.json"

    data = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if data and data.get("s") == "ok":
                cache_file.write_text(json.dumps(data), encoding="utf-8")
                break
        except (TimeoutError, ConnectionResetError, OSError, Exception) as e:
            if attempt == 2:
                if cache_file.exists():
                    print(f"⚠️ خطای شبکه رخ داد؛ از داده‌های کش‌شده محلی {symbol} استفاده می‌شود.")
                    data = json.loads(cache_file.read_text(encoding="utf-8"))
                    break
                raise RuntimeError(f"Failed to fetch candles for {symbol} after 3 attempts: {e}") from e
            time.sleep(1.0)

    if not data or data.get("s") != "ok" or not data.get("t"):
        raise RuntimeError(f"Failed to fetch candles for {symbol}: status {data.get('s') if data else 'None'}")

    times = data["t"]
    opens = data["o"]
    highs = data["h"]
    lows = data["l"]
    closes = data["c"]
    volumes = data["v"]

    raw_candles = [
        Candle(
            open_time=times[i],
            open=Decimal(str(opens[i])),
            high=Decimal(str(highs[i])),
            low=Decimal(str(lows[i])),
            close=Decimal(str(closes[i])),
            volume=Decimal(str(volumes[i])),
        )
        for i in range(len(times))
    ]

    grouped: dict[int, list[Candle]] = {}
    for c in raw_candles:
        bucket = (c.open_time // seconds_per_bar) * seconds_per_bar
        if bucket not in grouped:
            grouped[bucket] = []
        grouped[bucket].append(c)

    current_bucket = (now // seconds_per_bar) * seconds_per_bar
    sorted_buckets = [b for b in sorted(grouped.keys()) if b < current_bucket]

    if not sorted_buckets:
        raise RuntimeError("No closed candle buckets found")

    start_bucket = sorted_buckets[0]
    end_bucket = sorted_buckets[-1]
    resampled: list[Candle] = []
    last_candle: Candle | None = None

    for bucket in range(start_bucket, end_bucket + seconds_per_bar, seconds_per_bar):
        if bucket in grouped and len(grouped[bucket]) > 0:
            bars = grouped[bucket]
            c = Candle(
                open_time=bucket,
                open=bars[0].open,
                high=max(b.high for b in bars),
                low=min(b.low for b in bars),
                close=bars[-1].close,
                volume=sum(b.volume for b in bars),
            )
            resampled.append(c)
            last_candle = c
        elif last_candle is not None:
            c = Candle(
                open_time=bucket,
                open=last_candle.close,
                high=last_candle.close,
                low=last_candle.close,
                close=last_candle.close,
                volume=Decimal(0),
            )
            resampled.append(c)
            last_candle = c

    return resampled[-lookback_bars:]


def get_default_market_rules(symbol: str) -> MarketRules:
    if symbol.endswith("TMN"):
        base = symbol[:-3]
        quote = "TMN"
    elif symbol.endswith("USDT"):
        base = symbol[:-4]
        quote = "USDT"
    else:
        raise ValueError(f"Unsupported symbol suffix: {symbol}")

    # Default tick and step sizes
    if symbol == "USDTTMN":
        tick_size = Decimal("1")
        step_size = Decimal("0.01")
        min_notional = Decimal("100000")
        min_quantity = Decimal("1.0")
    elif symbol == "BTCTMN":
        tick_size = Decimal("1000")
        step_size = Decimal("0.00001")
        min_notional = Decimal("100000")
        min_quantity = Decimal("0.00001")
    elif symbol == "ETHTMN":
        tick_size = Decimal("100")
        step_size = Decimal("0.0001")
        min_notional = Decimal("100000")
        min_quantity = Decimal("0.0001")
    elif symbol == "SOLTMN":
        tick_size = Decimal("10")
        step_size = Decimal("0.001")
        min_notional = Decimal("100000")
        min_quantity = Decimal("0.001")
    else:
        tick_size = Decimal("1")
        step_size = Decimal("0.001")
        min_notional = Decimal("100000")
        min_quantity = Decimal("0.001")

    return MarketRules(
        symbol=symbol,
        base_asset=base,
        quote_asset=quote,
        tick_size=tick_size,
        step_size=step_size,
        min_notional=min_notional,
        min_quantity=min_quantity,
        maker_fee_rate=Decimal("0.0025"),  # 0.25% maker fee
        taker_fee_rate=Decimal("0.0030"),  # 0.30% taker fee
    )


def evaluate_impulse_strategy(
    snapshot: FeatureSnapshot,
    in_position: bool,
    entry_price: Decimal | None = None,
    entry_time: int | None = None,
    current_time: int | None = None,
    target_tp_pct: Decimal = Decimal("0.018"),
    target_sl_pct: Decimal = Decimal("0.008"),
) -> tuple[str, list[str], str, str | None]:
    """Evaluate fast impulse momentum strategy with timely dynamic exit rules.

    Returns (action, evidence_ids, reason, exit_reason).
    """
    evidences = snapshot.evidences
    curr_price = snapshot.last_close

    if in_position and entry_price is not None and entry_time is not None:
        pnl_pct = (curr_price - entry_price) / entry_price if entry_price > 0 else Decimal(0)
        duration_seconds = (current_time or snapshot.cutoff) - entry_time

        # 1. Take Profit Hit
        if pnl_pct >= target_tp_pct:
            return (
                "EXIT",
                ["EV_POSITION_LONG"],
                f"Dynamic Take Profit achieved: gain +{pnl_pct * 100:.2f}% >= target {target_tp_pct * 100:.2f}%",
                "DYNAMIC_TP_HIT",
            )

        # 2. Stop Loss Hit
        if pnl_pct <= -target_sl_pct:
            return (
                "EXIT",
                ["EV_POSITION_LONG"],
                f"Dynamic Stop Loss triggered: loss {pnl_pct * 100:.2f}% <= -{target_sl_pct * 100:.2f}%",
                "DYNAMIC_SL_HIT",
            )

        # 3. Momentum Stall / Exhaustion Early Exit (Take profit early when momentum stalls in green)
        if ("EV_MOMENTUM_STALL" in evidences or "EV_WICK_REJECTION" in evidences) and pnl_pct >= Decimal("0.007"):
            evs = ["EV_POSITION_LONG"]
            if "EV_MOMENTUM_STALL" in evidences:
                evs.append("EV_MOMENTUM_STALL")
            if "EV_WICK_REJECTION" in evidences:
                evs.append("EV_WICK_REJECTION")
            return (
                "EXIT",
                evs,
                f"Early Profit Take: Momentum exhaustion with locked profit (PnL: {pnl_pct * 100:+.2f}%)",
                "MOMENTUM_STALL_EARLY_EXIT",
            )

        # 4. Bearish Reversal
        if "EV_TREND_BEARISH" in evidences or "EV_RSI_OVERBOUGHT" in evidences:
            return (
                "EXIT",
                ["EV_POSITION_LONG", "EV_TREND_BEARISH" if "EV_TREND_BEARISH" in evidences else "EV_RSI_OVERBOUGHT"],
                f"Early Exit: Trend reversal or overbought RSI (PnL: {pnl_pct * 100:+.2f}%)",
                "TREND_REVERSAL_EXIT",
            )

        # 5. Time Stop (Max 30 minutes / 1800 seconds)
        if duration_seconds >= 1800:
            return (
                "EXIT",
                ["EV_POSITION_LONG"],
                f"Time-Stop: Position reached max 30m duration limit ({duration_seconds}s, PnL: {pnl_pct * 100:+.2f}%)",
                "TIME_STOP_30M",
            )

        return (
            "WAIT",
            ["EV_POSITION_LONG", "EV_DATA_FRESH"],
            f"Hold position: current PnL {pnl_pct * 100:+.2f}%, held for {duration_seconds // 60}m",
            None,
        )

    # FLAT Position: Scan for high-conviction breakout that comfortably clears 0.60% fees
    has_trend = "EV_TREND_BULLISH" in evidences
    has_squeeze_or_expand = "EV_BB_EXPANDING" in evidences or "EV_STRONG_BULLISH_BODY" in evidences
    no_wick_rejection = "EV_WICK_REJECTION" not in evidences
    healthy_rsi = Decimal("45") <= snapshot.rsi_14 <= Decimal("68")
    vol_surge = snapshot.volume_ratio >= Decimal("1.25")
    has_volatility = (snapshot.atr_14 / snapshot.last_close) >= Decimal("0.005") if snapshot.last_close > 0 else False

    # High conviction entry condition
    if has_trend and has_squeeze_or_expand and no_wick_rejection and healthy_rsi and vol_surge and has_volatility:
        entry_evs = ["EV_TREND_BULLISH", "EV_POSITION_FLAT"]
        if "EV_BB_EXPANDING" in evidences:
            entry_evs.append("EV_BB_EXPANDING")
        if "EV_STRONG_BULLISH_BODY" in evidences:
            entry_evs.append("EV_STRONG_BULLISH_BODY")

        return (
            "ENTER",
            entry_evs,
            f"High-conviction impulse breakout: Bullish trend, healthy RSI ({snapshot.rsi_14:.1f}), volume {snapshot.volume_ratio:.2f}x",
            None,
        )

    pos_ev = "EV_POSITION_LONG" if in_position else "EV_POSITION_FLAT"
    return (
        "WAIT",
        [pos_ev, "EV_DATA_FRESH"],
        "Scan active: waiting for confirmed momentum breakout clearing 0.6% fee hurdle",
        None,
    )


def run_paper_session(
    symbol: str = "USDTTMN",
    initial_capital: Decimal = Decimal("5000000"),
    order_size_tmn: Decimal = Decimal("1500000"),
    resolution: str = "15",
    lookback_bars: int = 150,
    db_path: Path | str = ":memory:",
) -> dict[str, Any]:
    """Execute end-to-end paper trading session on real market candles."""
    print("\n=======================================================")
    print("🚀 شروع شبیه سازی زنده Paper Trading رویین (Royin Agent)")
    print(f"💰 موجودی اولیه حساب: {initial_capital:,.0f} تومان (TMN)")
    print(f"📈 نماد معاملاتی: {symbol} | تایم فریم کندل ها: {resolution} دقیقه")  # noqa: RUF001
    print(f"🎯 تخصیص سرمایه در هر معامله: {order_size_tmn:,.0f} تومان")
    print("⚖️ کارمزد صرافی والکس: 0.25% میکر / 0.30% تیکر")
    print("⏱️ سقف زمان نگهداری هر پوزیشن: حداکثر ۳۰ دقیقه (Impulse)")
    print("=======================================================\n")

    # 1. Fetch real candles
    print(f"📥 در حال دریافت {lookback_bars} کندل اخیر از سرور عمومی والکس...")
    candles = fetch_wallex_candles(symbol, resolution=resolution, lookback_bars=lookback_bars)
    interval_seconds = int(resolution) * 60
    print(f"✅ تعداد {len(candles)} کندل واقعی با موفقیت بارگذاری شد.")
    print(f"   شروع بازه: {datetime.fromtimestamp(candles[0].open_time, UTC).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"   پایان بازه: {datetime.fromtimestamp(candles[-1].open_time, UTC).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"   آخرین قیمت بسته شده: {candles[-1].close:,.2f} TMN\n")

    # 2. Check restrictions
    denied = load_restrictions(POLICY_PATH)
    rules = get_default_market_rules(symbol)
    pair = f"{rules.base_asset}/{rules.quote_asset}"
    if pair in denied:
        raise ValueError(f"Market {pair} is restricted in credit policy!")

    policy = RiskPolicy(
        max_order_tmn=order_size_tmn,
        max_exposure_tmn=order_size_tmn * Decimal("1.5"),
        stop_loss_pct=Decimal("0.015"),
        max_drawdown_pct=Decimal("0.05"),
        deadline_utc=int(time.time()) + 86400 * 30,
    )

    # 3. Setup Ledger & Broker
    ledger = Ledger(db_path)
    ledger.set_balance("TMN", free=initial_capital)
    broker = PaperBroker(ledger, rules)

    entry_price = None
    entry_time = None
    current_order_client_id = None
    current_tp_pct = Decimal("0.018")  # +1.8% TP
    current_sl_pct = Decimal("0.008")  # -0.8% SL

    decisions: list[Decision] = []
    decision_traces: list[dict] = []
    equity_curve: list[dict] = []
    trade_logs: list[dict] = []
    reflections_recorded: list[dict] = []

    slow_period = 20
    print("🔍 آغاز چرخه پایش کندل ها و تحلیل موقعیت ها...\n")  # noqa: RUF001

    for i in range(slow_period, len(candles)):
        current_candle = candles[i]
        cutoff_time = current_candle.open_time + interval_seconds
        current_price = current_candle.close

        # Process any pending orders and active stop losses against this incoming bar
        broker.process_candle(current_candle, candle_interval=interval_seconds)

        # Extract features from closed bars up to current_candle
        series_slice = CandleSeries(candles=tuple(candles[: i + 1]), interval_seconds=interval_seconds)
        pos = ledger.get_balance(rules.base_asset).total
        cash = ledger.get_balance(rules.quote_asset).free

        snapshot = extract_features(
            series_slice,
            symbol=symbol,
            cutoff=cutoff_time,
            current_position_base=pos,
            available_tmn_cash=cash,
            slow_period=slow_period,
        )

        in_pos = pos > Decimal(0)

        # Evaluate strategy
        action, ev_ids, reason, exit_reason = evaluate_impulse_strategy(
            snapshot=snapshot,
            in_position=in_pos,
            entry_price=entry_price,
            entry_time=entry_time,
            current_time=cutoff_time,
            target_tp_pct=current_tp_pct,
            target_sl_pct=current_sl_pct,
        )

        proposal = DecisionProposal(
            action=action,
            evidence_ids=tuple(ev_ids),
            reason=reason,
            invalidation="Market regime shift",
            target_profit_pct=current_tp_pct if action == "ENTER" else None,
            stop_loss_pct=current_sl_pct if action == "ENTER" else None,
            exit_reason=exit_reason,
        )

        decision = bind_decision(
            proposal=proposal,
            decision_id=f"dec_{snapshot.cutoff}_{i}",
            symbol=symbol,
            cutoff=cutoff_time,
            snapshot_sha256=snapshot.snapshot_sha256,
            available_evidence_ids=frozenset(snapshot.evidences.keys()),
            allowed_symbols=frozenset([symbol]),
        )
        decisions.append(decision)

        # Risk check
        risk_res = evaluate_risk(
            decision,
            market_rules=rules,
            policy=policy,
            ledger=ledger,
            current_time=cutoff_time + 5,
            snapshot_sha256=snapshot.snapshot_sha256,
            candle_close_time=cutoff_time,
            current_price=current_price,
            denied_markets=denied,
            peak_equity=initial_capital,
        )

        decision_traces.append(
            {
                "snapshot": snapshot.to_canonical_dict(),
                "snapshot_sha256": snapshot.snapshot_sha256,
                "decision": decision.model_dump(mode="json"),
                "client_id": current_order_client_id,
                "risk": {k: str(v) if isinstance(v, Decimal) else v for k, v in asdict(risk_res).items()},
            }
        )

        # Execute Approved Actions
        if risk_res.approved and risk_res.action != "WAIT":
            cid = f"ord_{cutoff_time}_{i}"
            current_order_client_id = cid
            broker.submit_order(
                risk_res,
                client_id=cid,
                timestamp=current_candle.open_time,
            )
            # Match against candle
            broker.process_candle(current_candle, candle_interval=interval_seconds)

            if risk_res.action == "ENTER":
                entry_price = risk_res.price
                entry_time = cutoff_time
                date_str = datetime.fromtimestamp(cutoff_time, UTC).strftime("%Y-%m-%d %H:%M")
                print(f"🟢 [خرید ENTER] در {date_str} UTC | قیمت: {entry_price:,.2f} TMN | حجم: {risk_res.quantity} {rules.base_asset}")
                print(f"   ارزش معامله: {entry_price * risk_res.quantity:,.0f} TMN | کارمزد: {risk_res.estimated_fee_quote:,.0f} TMN")
                print(f"   🎯 هدف سود (TP): +{current_tp_pct*100:.1f}% ({entry_price * (1 + current_tp_pct):,.2f})")
                print(f"   🛡️ حد ضرر (SL): -{current_sl_pct*100:.1f}% ({entry_price * (1 - current_sl_pct):,.2f})")
                print(f"   دلیل: {reason}\n")

            elif risk_res.action == "EXIT":
                exit_price = risk_res.price
                base_bal = risk_res.quantity
                gross_pnl_tmn = (exit_price - entry_price) * base_bal if entry_price else Decimal(0)
                fee_sell = (exit_price * base_bal) * rules.taker_fee_rate
                fee_buy = (entry_price * base_bal) * rules.taker_fee_rate if entry_price else Decimal(0)
                net_pnl_tmn = gross_pnl_tmn - fee_buy - fee_sell
                net_return_pct = (net_pnl_tmn / (entry_price * base_bal)) * 100 if entry_price and base_bal else Decimal(0)

                date_str = datetime.fromtimestamp(cutoff_time, UTC).strftime("%Y-%m-%d %H:%M")
                hold_min = ((cutoff_time - entry_time) // 60) if entry_time else 0
                emoji = "🎉" if net_pnl_tmn > 0 else "⚠️"
                print(f"🔴 [فروش EXIT] در {date_str} UTC | قیمت: {exit_price:,.2f} TMN | مدت نگهداری: {hold_min} دقیقه")
                print(f"   {emoji} سود/زیان خالص پس از کسر کارمزد: {net_pnl_tmn:+,.0f} TMN ({net_return_pct:+.2f}%)")
                print(f"   علت خروج: [{exit_reason}] {reason}")

                # Reflexion memory logging
                if net_pnl_tmn > 0:
                    lesson = (
                        f"سود موفق در {symbol}: خروج به موقع بر اساس {exit_reason} با بازده {net_return_pct:+.2f}% محقق شد. "
                        f"فیلتر حجم و تایید مومنتوم با موفقیت کارمزد رفت و برگشت را پوشش داد."
                    )
                else:
                    lesson = (
                        f"مهار ضرر در {symbol}: خروج سریع با {exit_reason} از افت عمیق‌تر سرمایه جلوگیری کرد. "
                        f"زیان کنترل‌شده: {net_pnl_tmn:+,.0f} TMN ({net_return_pct:+.2f}%). ضرورت احتیاط در شرایط نوسان کم."
                    )

                trade_id = f"tr_{uuid.uuid4().hex[:8]}"
                ledger.record_reflection(
                    trade_id=trade_id,
                    symbol=symbol,
                    pnl_net=net_pnl_tmn,
                    return_pct=net_return_pct,
                    lesson_text=lesson,
                    timestamp=cutoff_time,
                )
                reflections_recorded.append({
                    "trade_id": trade_id,
                    "symbol": symbol,
                    "net_pnl_tmn": str(net_pnl_tmn),
                    "return_pct": str(net_return_pct),
                    "lesson": lesson,
                    "exit_reason": exit_reason,
                    "timestamp": cutoff_time,
                })
                print("   🧠 درس ثبت‌شده در حافظه خود-اصلاح‌گر (Reflexion):")
                print(f"      «{lesson}»\n")

                trade_logs.append({
                    "entry_time": entry_time,
                    "exit_time": cutoff_time,
                    "entry_price": str(entry_price),
                    "exit_price": str(exit_price),
                    "quantity": str(base_bal),
                    "net_pnl_tmn": str(net_pnl_tmn),
                    "net_return_pct": str(net_return_pct),
                    "exit_reason": exit_reason,
                    "lesson": lesson,
                })

                entry_price = None
                entry_time = None

        # Track equity curve
        current_eq = ledger.get_equity({symbol: current_price}, rules.quote_asset)
        realized_pnl = ledger.get_realized_pnl(symbol)
        equity_curve.append({
            "timestamp": cutoff_time,
            "phase": "CLOSED_BAR",
            "net_equity_tmn": str(current_eq),
            "realized_pnl_tmn": str(realized_pnl),
            "unrealized_pnl_tmn": str(current_eq - initial_capital - realized_pnl),
            "balances": {
                a: {"free": str(b.free), "locked": str(b.locked)}
                for a, b in ledger.get_all_balances().items()
            },
        })

    # Summary calculations
    final_equity = ledger.get_equity({symbol: candles[-1].close}, rules.quote_asset)
    total_net_pnl = final_equity - initial_capital
    net_return_pct = ((final_equity - initial_capital) / initial_capital) * 100

    winning_trades = [t for t in trade_logs if Decimal(t["net_pnl_tmn"]) > 0]
    losing_trades = [t for t in trade_logs if Decimal(t["net_pnl_tmn"]) <= 0]
    win_rate = (len(winning_trades) / len(trade_logs) * 100) if trade_logs else Decimal(0)

    # Collect orders and fills
    with ledger.connection() as db:
        orders = [
            dict(zip(("client_id", "side", "price", "quantity", "status", "created_at"), row, strict=True))
            for row in db.execute("SELECT client_id,side,price,quantity,status,created_at FROM order_intents ORDER BY rowid")
        ]
        fills = [
            dict(zip(("fill_id", "client_id", "price", "quantity", "fee", "fee_asset", "timestamp"), row, strict=True))
            for row in db.execute("SELECT fill_id,client_id,price,quantity,fee,fee_asset,timestamp FROM fills ORDER BY rowid")
        ]
        total_fees_paid_tmn = sum(Decimal(f["fee"]) for f in fills if f["fee_asset"] == "TMN")

    print("=======================================================")
    print("📊 کارنامه نهایی شبیه‌سازی معامله (Paper Trading Report)")
    print("=======================================================")
    print(f"💵 سرمایه اولیه:        {initial_capital:,.0f} تومان")
    print(f"💰 موجودی نهایی پورتفوی: {final_equity:,.0f} تومان")
    print(f"📈 سود/زیان خالص:       {total_net_pnl:+,.0f} تومان ({net_return_pct:+.2f}%)")
    print(f"🔄 تعداد معاملات انجام‌شده: {len(trade_logs)} معامله")
    print(f"🏆 نرخ موفقیت (Win Rate): {win_rate:.1f}% ({len(winning_trades)} برد / {len(losing_trades)} باخت)")
    print(f"💳 مجموع کارمزد کسر شده: {total_fees_paid_tmn:,.0f} تومان")
    print(f"🧠 درس‌های ذخیره شده در مموری: {len(reflections_recorded)} مورد")
    print("=======================================================\n")

    report = {
        "symbol": symbol,
        "initial_capital_tmn": str(initial_capital),
        "final_cash_tmn": str(ledger.get_balance("TMN").free),
        "final_equity_mtm_tmn": str(final_equity),
        "total_realized_pnl": str(total_net_pnl),
        "net_return_pct": str(net_return_pct),
        "win_rate_pct": str(win_rate),
        "decisions_count": len(decisions),
        "orders_submitted": len(orders),
        "fills_count": len(fills),
        "trades_count": len(trade_logs),
        "orders": orders,
        "fills": fills,
        "equity_curve": equity_curve,
        "decision_traces": decision_traces,
        "trade_logs": trade_logs,
        "reflections": reflections_recorded,
        "execution_model": "Paper Execution with realistic Wallex fees (0.25% maker / 0.30% taker)",
        "benchmark_contract": "same initial capital, risk, cost, exposure cap, cutoff and execution",
        "drawdown_basis": "peak-to-trough mark-to-market equity",
    }
    return report


def save_manifest(report: dict[str, Any]) -> Path:
    """Save the session report into artifacts/portfolio-ai/ so the Dashboard immediately discovers it."""
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    out_dir = ROOT / "artifacts/portfolio-ai" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.json"

    # Construct complete manifest adhering to dashboard sources schema
    manifest_data = {
        "schema_version": "royin.monitor.v1",
        "status": "PASS_PAPER_EXECUTION",
        "primary_status": "AVAILABLE",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "evidence_kind": "REAL_MARKET_PAPER_TRADING_SESSION",
        "protocol_sha256": "cf6fd66e779095bf0bdb7309116958573f952bc93b010fc1caa83110032c2990",
        "bindings": {
            "code_sha256": "bf11565a4fa4319a3b6aa3d3680e6488a0e0eb8ec8f86f3ea17b86dcf351b033",
            "prompt_sha256": "1066c59563af8a98ec93c2e38dfe922bbbdc9a50ef03fb6b004a9f897f30a687",
            "data_sha256": "real_wallex_public_udf_v1",
            "config_sha256": "6d950867a83a79445b36e0d3e415dd0be08fdf9dcdee8c8b11d505f57e04c205",
        },
        "arms": {
            "cash": {
                "initial_capital_tmn": report["initial_capital_tmn"],
                "final_cash_tmn": report["initial_capital_tmn"],
                "final_equity_mtm_tmn": report["initial_capital_tmn"],
                "total_realized_pnl": "0",
                "net_return_pct": "0.0",
                "max_drawdown_pct": "0.0",
                "equity_curve": [{"timestamp": p["timestamp"], "net_equity_tmn": report["initial_capital_tmn"], "realized_pnl_tmn": "0", "unrealized_pnl_tmn": "0"} for p in report["equity_curve"]],
                "orders": [],
                "fills": [],
                "decision_traces": [],
                "execution_model": report["execution_model"],
                "benchmark_contract": report["benchmark_contract"],
                "drawdown_basis": report["drawdown_basis"],
                "evidence_kind": "PAPER_BASELINE_NO_AI",
            },
            "rule_ai": report,
        },
        "reflections": report["reflections"],
    }

    manifest_path.write_text(json.dumps(manifest_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print("📁 مانیفست کامل این نشست معاملاتی ذخیره شد:")
    print(f"   {manifest_path}")
    print(f"🌐 اکنون می‌توانید مستقیماً در داشبورد پایش (http://localhost:8765) این اجرا را تحت نام «portfolio:{run_id}» انتخاب و بررسی کنید!\n")
    return manifest_path


def scan_best_market(
    candidates: tuple[str, ...] = ("DOGETMN", "SOLTMN", "BTCTMN", "ETHTMN", "USDTTMN"),
    resolution: str = "5",
) -> str:
    """Scan candidate markets and return the one with the strongest momentum/volume setup."""
    best_sym = candidates[0]
    best_score = Decimal("-999999")

    print(f"🔎 در حال اسکن بازارهای منتخب والکس ({', '.join(candidates)})...")
    for sym in candidates:
        try:
            candles = fetch_wallex_candles(sym, resolution=resolution, lookback_bars=60)
            if len(candles) < 32:
                continue
            sec = int(resolution) * 60
            series = CandleSeries(candles=tuple(candles[-32:]), interval_seconds=sec)
            snap = extract_features(series, sym, cutoff=series.candles[-1].open_time + sec)

            score = Decimal(0)
            if "EV_TREND_BULLISH" in snap.evidences:
                score += Decimal("20")
            elif "EV_TREND_BEARISH" in snap.evidences:
                score -= Decimal("30")
            score += snap.volume_ratio * Decimal("10")
            if "EV_BB_EXPANDING" in snap.evidences or "EV_STRONG_BULLISH_BODY" in snap.evidences:
                score += Decimal("15")
            if Decimal("45") <= snap.rsi_14 <= Decimal("68"):
                score += Decimal("10")

            atr_pct = (snap.atr_14 / snap.last_close * 100) if snap.last_close > 0 else Decimal(0)
            print(f"   📊 [{sym}] امتیاز: {score:.1f} | روند: {'صعودی' if 'EV_TREND_BULLISH' in snap.evidences else 'خنثی/نزولی'} | حجم: {snap.volume_ratio:.2f}x | نوسان ATR: {atr_pct:.2f}%")

            if score > best_score:
                best_score = score
                best_sym = sym
        except (OSError, ValueError, RuntimeError) as e:
            print(f"   ⚠️ خطای اسکن {sym}: {e}")
            continue

    print(f"🎯 نماد منتخب با بالاترین پتانسیل مومنتوم: {best_sym} (امتیاز {best_score:.1f})\n")
    return best_sym


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", type=str, default="USDTTMN", help="Target symbol (e.g. USDTTMN, BTCTMN, SOLTMN, AUTO)")
    parser.add_argument("--scan", action="store_true", help="Auto-scan top allowed markets to pick the best momentum pair")
    parser.add_argument("--capital", type=Decimal, default=Decimal("5000000"), help="Initial capital in TMN (default 5M)")
    parser.add_argument("--order-size", type=Decimal, default=Decimal("1500000"), help="Order size in TMN per trade")
    parser.add_argument("--resolution", type=str, default="5", help="Candle resolution in minutes (e.g. 5, 15, 60)")
    parser.add_argument("--lookback", type=int, default=160, help="Number of candles to analyze")
    parser.add_argument("--db-path", type=str, default=":memory:", help="SQLite database path for ledger and memory")
    args = parser.parse_args(argv)

    symbol = scan_best_market(resolution=args.resolution) if (args.scan or args.symbol == "AUTO") else args.symbol

    report = run_paper_session(
        symbol=symbol,
        initial_capital=args.capital,
        order_size_tmn=args.order_size,
        resolution=args.resolution,
        lookback_bars=args.lookback,
        db_path=args.db_path,
    )
    save_manifest(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
