import os
import warnings
from datetime import datetime
import pandas as pd

warnings.filterwarnings("ignore")

# ===================== STRATEGIA ETF BASE - SOLO PAPER TRADING =====================
RISCHIO = ["SPY", "QQQ", "IWM", "EFA", "EEM", "VNQ", "GLD", "TLT", "IEF"]
CASH = "SHY"
UNIVERSO = RISCHIO + [CASH]
FINESTRE = [63, 126, 252]
TOP_N = 3
USO_CAPITALE = 0.995
MIN_ORDINE = 25.0
BANDA = 0.01
FILE_LOG = "log_ordini_etf.csv"
FUSO = "America/New_York"

def scarica_prezzi():
    import yfinance as yf
    d = yf.download(UNIVERSO, period="3y", auto_adjust=True, progress=False)["Close"]
    d = d.dropna(how="any")
    adesso = pd.Timestamp.now(tz=FUSO)
    if len(d) and d.index[-1] >= adesso.normalize().tz_localize(None) and adesso.hour < 16:
        d = d.iloc[:-1]
    return d

def calcola_pesi(prezzi):
    if len(prezzi) < max(FINESTRE) + 2:
        raise SystemExit("Dati insufficienti per calcolare il segnale.")
    ult = prezzi.iloc[-1]
    s = sum(ult / prezzi.iloc[-1 - n] - 1 for n in FINESTRE) / len(FINESTRE)
    cand = s[RISCHIO]
    cand = cand[cand > s[CASH]].nlargest(TOP_N)
    w = pd.Series(0.0, index=UNIVERSO)
    for t in cand.index:
        w[t] = 1.0 / TOP_N
    w[CASH] = 1.0 - w.sum()
    return s, w

def leggi_chiavi():
    chiave = os.environ.get("ALPACA_API_KEY")
    segreto = os.environ.get("ALPACA_SECRET_KEY")
    if not (chiave and segreto):
        raise SystemExit("Chiavi API mancanti nelle variabili d'ambiente.")
    return chiave.strip(), segreto.strip()

def main(invia=True):
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import MarketOrderRequest, GetOrdersRequest
    from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus

    chiave, segreto = leggi_chiavi()
    client = TradingClient(chiave, segreto, paper=True)
    acc = client.get_account()
    if getattr(acc, "trading_blocked", False):
        print("Il conto risulta bloccato per il trading: controlla la dashboard di Alpaca.")
        return
    equity = float(acc.equity)
    print(f"Conto PAPER (simulato) - valore: {equity:,.2f} USD")

    prezzi = scarica_prezzi()
    s, pesi = calcola_pesi(prezzi)
    print(f"\nDati di prezzo fino al {prezzi.index[-1].date()}")
    print("\nClassifica momentum (media 3/6/12 mesi):")
    for t, v in s.sort_values(ascending=False).items():
        tag = "  <- liquidita' di riferimento" if t == CASH else ("  <- scelto" if pesi[t] > 0 else "")
        print(f"  {t:5s}{v:>8.1%}{tag}")
    print("\nPortafoglio target:")
    for t, p in pesi[pesi > 0].sort_values(ascending=False).items():
        print(f"  {t:5s}{p:>7.1%}")

    posizioni = {p.symbol: float(p.market_value) for p in client.get_all_positions()}
    altre = {t: v for t, v in posizioni.items() if t not in UNIVERSO}
    if altre:
        print(f"\nAttenzione: nel conto ci sono altre posizioni che il bot NON tocca: {', '.join(altre)}")
    base = (equity - sum(altre.values())) * USO_CAPITALE

    aperti = client.get_orders(filter=GetOrdersRequest(status=QueryOrderStatus.OPEN))
    if aperti:
        print(f"\nCi sono {len(aperti)} ordini ancora aperti nel conto. Per evitare doppioni non faccio nulla.")
        return

    ordini = []
    for t in UNIVERSO:
        attuale = posizioni.get(t, 0.0)
        diff = pesi[t] * base - attuale
        chiudi = pesi[t] == 0 and attuale > 0
        if chiudi or abs(diff) >= max(MIN_ORDINE, BANDA * equity):
            ordini.append((t, diff, chiudi))
    ordini.sort(key=lambda x: x[1])

    if not ordini:
        print("\nNessun ordine necessario: il conto e' gia' allineato al portafoglio target.")
        return
    print("\nOrdini necessari:")
    for t, diff, chiudi in ordini:
        print(f"  {'VENDI TUTTO' if chiudi else ('COMPRA' if diff > 0 else 'VENDI'):12s}{t:5s}{abs(diff):>12,.2f} USD")

    if not invia:
        print("\nSIMULAZIONE: nessun ordine inviato.")
        return
    if not client.get_clock().is_open:
        print("\nIl mercato USA e' chiuso: gli ordini frazionati vanno inviati a mercato aperto.")
        return

    nuovo = not os.path.exists(FILE_LOG)
    with open(FILE_LOG, "a", encoding="utf-8") as f:
        if nuovo:
            f.write("data,ticker,lato,importo_usd,esito\n")
        for t, diff, chiudi in ordini:
            lato, esito = ("VENDI_TUTTO" if chiudi else ("COMPRA" if diff > 0 else "VENDI")), "ok"
            try:
                if chiudi:
                    client.close_position(t)
                else:
                    asset = client.get_asset(t)
                    if not getattr(asset, "tradable", True):
                        raise RuntimeError("titolo non negoziabile")
                    side = OrderSide.BUY if diff > 0 else OrderSide.SELL
                    if getattr(asset, "fractionable", True):
                        req = MarketOrderRequest(symbol=t, notional=round(abs(diff), 2), side=side, time_in_force=TimeInForce.DAY)
                    else:
                        qty = int(abs(diff) // float(prezzi.iloc[-1][t]))
                        if qty < 1:
                            esito = "saltato (meno di 1 azione)"
                            req = None
                        else:
                            req = MarketOrderRequest(symbol=t, qty=qty, side=side, time_in_force=TimeInForce.DAY)
                    if req is not None:
                        client.submit_order(order_data=req)
            except Exception as e:
                esito = f"ERRORE: {e}"
            print(f"  {lato:12s}{t:5s}{abs(diff):>12,.2f} USD  -> {esito}")
            f.write(f"{datetime.now():%Y-%m-%d %H:%M},{t},{lato},{abs(diff):.2f},{esito}\n")
    print("\nFatto. Controlla le posizioni su app.alpaca.markets (modalita' Paper).")

if __name__ == "__main__":
    main(invia=True)
