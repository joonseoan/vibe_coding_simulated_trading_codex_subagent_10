"use client";

import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

interface MainChartProps { ticker: string | null; priceHistory: Record<string, { price: number; time: string }[]>; }

export default function MainChart({ ticker, priceHistory }: MainChartProps) {
  const data = ticker ? priceHistory[ticker] ?? [] : [];
  if (!ticker) return <Empty text="Select a ticker from the watchlist" />;
  if (data.length < 2) return <div className="flex h-full flex-col"><div className="text-sm font-semibold text-accent-yellow">{ticker} <span className="text-xs font-normal text-text-secondary">session price</span></div><Empty text="Waiting for session prices..." /></div>;
  const values = data.map((point) => point.price);
  const padding = (Math.max(...values) - Math.min(...values)) * 0.15 || 1;
  return <div className="flex h-full min-h-0 flex-col"><div className="text-sm font-semibold text-accent-yellow">{ticker} <span className="text-xs font-normal text-text-secondary">session price</span></div><div className="min-h-0 flex-1"><ResponsiveContainer width="100%" height="100%"><LineChart data={data} margin={{ top: 8, right: 10, bottom: 0, left: 2 }}><XAxis dataKey="time" tickFormatter={(v: string) => new Date(v).toLocaleTimeString([], { minute: "2-digit", second: "2-digit" })} tick={{ fontSize: 10, fill: "#8b949e" }} tickLine={false} axisLine={false} minTickGap={45}/><YAxis domain={[Math.min(...values) - padding, Math.max(...values) + padding]} tickFormatter={(v: number) => `$${v.toFixed(2)}`} tick={{ fontSize: 10, fill: "#8b949e" }} tickLine={false} axisLine={false} width={60}/><Tooltip contentStyle={{ background: "#161b22", border: "1px solid #30363d", fontSize: 11 }} labelFormatter={(v) => new Date(String(v)).toLocaleTimeString()} formatter={(v) => [`$${Number(v).toFixed(2)}`, ticker]}/><Line type="monotone" dataKey="price" stroke="#209dd7" strokeWidth={2} dot={false} isAnimationActive={false}/></LineChart></ResponsiveContainer></div></div>;
}
function Empty({ text }: { text: string }) { return <div className="flex min-h-0 flex-1 items-center justify-center text-sm text-text-secondary">{text}</div>; }
