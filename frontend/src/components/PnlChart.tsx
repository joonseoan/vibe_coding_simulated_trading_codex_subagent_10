"use client";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
export interface PortfolioPoint { time: string; value: number; }
export default function PnlChart({ data }: { data: PortfolioPoint[] }) {
  if (data.length < 2) return <div className="flex h-full items-center justify-center text-xs text-text-secondary">Waiting for session data...</div>;
  const values = data.map((point) => point.value); const padding = (Math.max(...values) - Math.min(...values)) * .15 || 10;
  return <ResponsiveContainer width="100%" height="100%"><LineChart data={data} margin={{ top: 4, right: 5, bottom: 2, left: 0 }}><XAxis dataKey="time" tickFormatter={(v: string) => new Date(v).toLocaleTimeString([], { minute: "2-digit", second: "2-digit" })} tick={{ fontSize: 9, fill: "#8b949e" }} tickLine={false} axisLine={false} minTickGap={40}/><YAxis domain={[Math.min(...values) - padding, Math.max(...values) + padding]} tick={{ fontSize: 9, fill: "#8b949e" }} tickLine={false} axisLine={false} tickFormatter={(v: number) => `$${v.toFixed(0)}`} width={48}/><Tooltip contentStyle={{ background: "#161b22", border: "1px solid #30363d", fontSize: 11 }} formatter={(v) => [`$${Number(v).toFixed(2)}`, "Value"]}/><Line type="monotone" dataKey="value" stroke="#209dd7" strokeWidth={1.5} dot={false} isAnimationActive={false}/></LineChart></ResponsiveContainer>;
}
