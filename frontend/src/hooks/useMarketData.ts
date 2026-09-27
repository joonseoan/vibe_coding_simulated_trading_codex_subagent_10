"use client";

import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import type { ConnectionStatus } from "@/components/Header";

export interface PriceUpdate {
  ticker: string;
  price: number;
  previous_price: number;
  timestamp: string;
  direction: "up" | "down" | "flat";
}

export type PriceMap = Record<string, PriceUpdate>;
export type PriceHistory = Record<string, { price: number; time: string }[]>;

const MAX_HISTORY = 500;

export function useMarketData() {
  const [prices, setPrices] = useState<PriceMap>({});
  const [status, setStatus] = useState<ConnectionStatus>("disconnected");
  const historyRef = useRef<PriceHistory>({});
  const [historyVersion, setHistoryVersion] = useState(0);
  const applyPrice = useCallback((update: PriceUpdate) => {
    if (!update.ticker || !Number.isFinite(update.price) || !update.timestamp) return;
    const normalized = { ...update, ticker: update.ticker.trim().toUpperCase() };
    setPrices((previous) => ({ ...previous, [normalized.ticker]: normalized }));
    const history = historyRef.current[normalized.ticker] ?? [];
    history.push({ price: normalized.price, time: normalized.timestamp });
    historyRef.current[normalized.ticker] = history.length > MAX_HISTORY ? history.slice(-MAX_HISTORY) : history;
    setHistoryVersion((version) => version + 1);
  }, []);

  useEffect(() => {
    const source = new EventSource("/api/stream/prices");
    source.onopen = () => setStatus("connected");
    const onPrice = (event: MessageEvent<string>) => {
      try { applyPrice(JSON.parse(event.data) as PriceUpdate); } catch { /* Ignore malformed events without dropping SSE. */ }
    };
    source.addEventListener("price", onPrice as EventListener);
    source.onerror = () => setStatus(source.readyState === EventSource.CLOSED ? "disconnected" : "reconnecting");
    return () => source.close();
  }, [applyPrice]);

  // Snapshot ref into a render-safe value keyed on historyVersion
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const priceHistory = useMemo(() => ({ ...historyRef.current }), [historyVersion]);

  return {
    prices,
    connectionStatus: status,
    priceHistory,
    historyVersion,
  };
}
