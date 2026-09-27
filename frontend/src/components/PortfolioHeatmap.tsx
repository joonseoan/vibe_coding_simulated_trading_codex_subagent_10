"use client";
import { ResponsiveContainer, Treemap } from "recharts";
import type { Position } from "@/lib/api";
import type { PriceMap } from "@/hooks/useMarketData";
interface Props { positions: Position[]; prices: PriceMap; }
type Node = { name: string; size: number; pnl: number; };
export default function PortfolioHeatmap({ positions, prices }: Props) {
  const data: Node[] = positions.map((position) => { const price = prices[position.ticker]?.price ?? position.current_price; return { name: position.ticker, size: Math.max(price * position.quantity, .01), pnl: position.avg_cost ? ((price - position.avg_cost) / position.avg_cost) * 100 : 0 }; });
  if (!data.length) return <div className="flex h-full items-center justify-center text-xs text-text-secondary">No positions</div>;
  return <ResponsiveContainer width="100%" height="100%"><Treemap data={data} dataKey="size" stroke="#161b22" content={<Tile />} isAnimationActive={false}/></ResponsiveContainer>;
}
function Tile(props: { x?: number; y?: number; width?: number; height?: number; name?: string; pnl?: number }) { const { x = 0, y = 0, width = 0, height = 0, name = "", pnl = 0 } = props; const color = pnl >= 0 ? `rgba(63,185,80,${.2 + Math.min(pnl / 10, 1) * .45})` : `rgba(248,81,73,${.2 + Math.min(-pnl / 10, 1) * .45})`; return <g><rect x={x} y={y} width={width} height={height} fill={color}/>{width > 42 && height > 25 && <text x={x + width / 2} y={y + height / 2 - 3} textAnchor="middle" fill="#e6edf3" fontSize="10" fontWeight="bold">{name}</text>}{width > 42 && height > 40 && <text x={x + width / 2} y={y + height / 2 + 10} textAnchor="middle" fill="#e6edf3" fontSize="9">{pnl >= 0 ? "+" : ""}{pnl.toFixed(1)}%</text>}</g>; }
