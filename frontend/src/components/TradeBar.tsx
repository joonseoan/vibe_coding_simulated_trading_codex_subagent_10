"use client";

import { useState } from "react";
import { api } from "@/lib/api";

interface TradeBarProps { onTradeExecuted: () => void; ticker?: string | null; }

export default function TradeBar({ onTradeExecuted, ticker: selectedTicker }: TradeBarProps) {
  const [ticker, setTicker] = useState("");
  const [quantity, setQuantity] = useState("");
  const [status, setStatus] = useState<string | null>(null);

  async function executeTrade(side: "buy" | "sell") {
    const activeTicker = ticker.trim() || selectedTicker || "";
    const qty = Number(quantity);
    if (!activeTicker || !Number.isFinite(qty) || qty < 0.0001) { setStatus("Enter a ticker and quantity of at least 0.0001"); return; }

    try {
      const result = await api.trade({
        ticker: activeTicker.toUpperCase(),
        quantity: qty,
        side,
      });
      const trade = result.trade;
      setStatus(`${trade.side.toUpperCase()} ${trade.quantity} ${trade.ticker} @ $${trade.price.toFixed(2)}`);
      setQuantity("");
      onTradeExecuted();
      setTimeout(() => setStatus(null), 3000);
    } catch (err) {
      setStatus(`Error: ${err instanceof Error ? err.message : "Trade failed"}`);
      setTimeout(() => setStatus(null), 3000);
    }
  }

  return (
    <div className="flex h-full items-center gap-3 text-xs">
      <input
        type="text"
        placeholder="Ticker"
        value={ticker}
        onChange={(e) => setTicker(e.target.value)}
        className="w-24 rounded border border-border bg-bg-secondary px-2 py-1 text-text-primary outline-none focus:border-accent-blue"
      />
      <input
        type="number"
        placeholder="Qty"
        value={quantity}
        onChange={(e) => setQuantity(e.target.value)}
        min="0.0001"
        step="0.0001"
        className="w-20 rounded border border-border bg-bg-secondary px-2 py-1 text-text-primary outline-none focus:border-accent-blue"
      />
      <button
        onClick={() => executeTrade("buy")}
        className="rounded bg-green px-3 py-1 font-semibold text-bg-primary hover:brightness-110"
      >
        BUY
      </button>
      <button
        onClick={() => executeTrade("sell")}
        className="rounded bg-red px-3 py-1 font-semibold text-bg-primary hover:brightness-110"
      >
        SELL
      </button>
      {status && (
        <span className="text-text-secondary">{status}</span>
      )}
    </div>
  );
}
