"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import Header from "@/components/Header";
import Panel from "@/components/Panel";
import ChatPanel from "@/components/ChatPanel";
import Watchlist from "@/components/Watchlist";
import MainChart from "@/components/MainChart";
import PortfolioHeatmap from "@/components/PortfolioHeatmap";
import PnlChart, { type PortfolioPoint } from "@/components/PnlChart";
import PositionsTable from "@/components/PositionsTable";
import TradeBar from "@/components/TradeBar";
import { useMarketData } from "@/hooks/useMarketData";
import { api, type PortfolioResponse, type Trade } from "@/lib/api";

const emptyPortfolio: PortfolioResponse = { cash_balance: 0, total_value: 0, positions: [] };
function liveValue(portfolio: PortfolioResponse, prices: Record<string, { price: number }>) { return portfolio.cash_balance + portfolio.positions.reduce((sum, position) => sum + (prices[position.ticker]?.price ?? position.current_price) * position.quantity, 0); }
export default function Home() {
  const { prices, connectionStatus, priceHistory, historyVersion } = useMarketData();
  const [portfolio, setPortfolio] = useState<PortfolioResponse>(emptyPortfolio); const [selectedTicker, setSelectedTicker] = useState<string | null>(null); const [trades, setTrades] = useState<Trade[]>([]); const [watchlistVersion, setWatchlistVersion] = useState(0); const [points, setPoints] = useState<PortfolioPoint[]>([]); const [resetting, setResetting] = useState(false);
  const refreshPortfolio = useCallback(async () => { try { setPortfolio(await api.getPortfolio()); } catch { /* API may still be starting */ } }, []);
  const refreshTrades = useCallback(async () => { try { setTrades(await api.getTrades()); } catch { /* leave last blotter */ } }, []);
  const refreshAll = useCallback(async () => { await Promise.all([refreshPortfolio(), refreshTrades()]); }, [refreshPortfolio, refreshTrades]);
  useEffect(() => { void refreshAll(); const timer = window.setInterval(() => void refreshPortfolio(), 10_000); return () => window.clearInterval(timer); }, [refreshAll, refreshPortfolio]);
  useEffect(() => { if (!selectedTicker) { const first = Object.keys(priceHistory)[0]; if (first) setSelectedTicker(first); } }, [priceHistory, selectedTicker]);
  useEffect(() => { if (!historyVersion) return; const latest = Object.values(prices).sort((a, b) => b.timestamp.localeCompare(a.timestamp))[0]; if (!latest) return; const point = { time: latest.timestamp, value: Number(liveValue(portfolio, prices).toFixed(2)) }; setPoints((old) => [...old.slice(-499), point]); }, [historyVersion, portfolio, prices]);
  const displayedValue = useMemo(() => liveValue(portfolio, prices), [portfolio, prices]);
  async function reset() { if (!window.confirm("Reset cash, positions, trades, chat, and watchlist?")) return; setResetting(true); try { const response = await api.reset(); setPortfolio(response.portfolio); setTrades([]); setPoints([]); setSelectedTicker(response.watchlist[0]?.ticker ?? null); setWatchlistVersion((value) => value + 1); } finally { setResetting(false); } }
  return <div className="flex h-screen min-w-[900px] flex-col overflow-hidden"><Header totalValue={displayedValue} cashBalance={portfolio.cash_balance} connectionStatus={connectionStatus} onReset={() => void reset()} resetting={resetting}/><div className="flex min-h-0 flex-1"><main className="flex min-w-0 flex-1 flex-col gap-1 p-1"><div className="flex min-h-0 flex-1 gap-1"><Panel title="Watchlist · session change" className="w-72 shrink-0 overflow-auto"><Watchlist prices={prices} priceHistory={priceHistory} selectedTicker={selectedTicker} onSelectTicker={setSelectedTicker} refreshKey={watchlistVersion}/></Panel><Panel title="Chart" className="min-w-0 flex-1"><MainChart ticker={selectedTicker} priceHistory={priceHistory}/></Panel><div className="flex w-80 shrink-0 flex-col gap-1"><Panel title="Portfolio Heatmap" className="flex-1"><PortfolioHeatmap positions={portfolio.positions} prices={prices}/></Panel><Panel title="P&L · session" className="flex-1"><PnlChart data={points}/></Panel><Panel title="Positions" className="flex-1 overflow-auto"><PositionsTable positions={portfolio.positions} prices={prices}/></Panel></div></div><div className="flex h-36 shrink-0 gap-1"><Panel title="Trade" className="flex-1"><TradeBar ticker={selectedTicker} onTradeExecuted={() => void refreshAll()}/></Panel><Panel title="Trade Blotter" className="w-1/2 overflow-auto"><Blotter trades={trades}/></Panel></div></main><ChatPanel onPortfolio={setPortfolio} onWatchlistRefresh={() => setWatchlistVersion((value) => value + 1)}/></div></div>;
}
function Blotter({ trades }: { trades: Trade[] }) { if (!trades.length) return <div className="text-xs text-text-secondary">No executed trades</div>; return <table className="w-full text-xs"><thead className="text-left text-text-secondary"><tr><th>Ticker</th><th>Side</th><th className="text-right">Qty</th><th className="text-right">Fill</th><th className="text-right">Time</th></tr></thead><tbody>{trades.map((trade) => <tr key={trade.id} className="border-t border-border/50"><td className="py-1 font-semibold text-accent-yellow">{trade.ticker}</td><td className={trade.side === "buy" ? "text-green" : "text-red"}>{trade.side.toUpperCase()}</td><td className="text-right">{trade.quantity}</td><td className="text-right">${trade.price.toFixed(2)}</td><td className="text-right text-text-secondary">{new Date(trade.executed_at).toLocaleTimeString()}</td></tr>)}</tbody></table>; }
