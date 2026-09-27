const BASE = "/api";

export class ApiError extends Error {
  constructor(public readonly status: number, public readonly code?: string, message?: string) {
    super(message ?? `API request failed (${status})`);
    this.name = "ApiError";
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { headers: { "Content-Type": "application/json", ...init?.headers }, ...init });
  if (!res.ok) {
    let payload: { error?: { code?: string; message?: string } } | undefined;
    try { payload = await res.json(); } catch { /* retain status error */ }
    throw new ApiError(res.status, payload?.error?.code, payload?.error?.message ?? `API ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  getPortfolio: () => apiFetch<PortfolioResponse>("/portfolio"),
  trade: (body: TradeRequest) =>
    apiFetch<TradeResponse>("/portfolio/trade", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  getTrades: () => apiFetch<Trade[]>("/portfolio/trades"),
  reset: () => apiFetch<ResetResponse>("/portfolio/reset", { method: "POST" }),
  getWatchlist: () => apiFetch<WatchlistItem[]>("/watchlist"),
  addTicker: (ticker: string) =>
    apiFetch<WatchlistItem>("/watchlist", {
      method: "POST",
      body: JSON.stringify({ ticker }),
    }),
  removeTicker: (ticker: string) => apiFetch<{ ok: true }>(`/watchlist/${encodeURIComponent(ticker)}`, { method: "DELETE" }),
  chat: (message: string) => apiFetch<ChatResponse>("/chat", { method: "POST", body: JSON.stringify({ message }) }),
  getChatHistory: () => apiFetch<ChatHistoryMessage[]>("/chat/history"),
};

/* Types matching backend API responses */

export interface PortfolioResponse {
  cash_balance: number;
  total_value: number;
  positions: Position[];
}

export interface Position {
  ticker: string;
  quantity: number;
  avg_cost: number;
  current_price: number;
  unrealized_pnl: number;
  pnl_percent: number;
}

export interface TradeRequest {
  ticker: string;
  quantity: number;
  side: "buy" | "sell";
}

export interface Trade { id: string; ticker: string; side: "buy" | "sell"; quantity: number; price: number; executed_at: string; }
export interface TradeResponse { trade: Trade; cash_balance: number; position: Pick<Position, "ticker" | "quantity" | "avg_cost"> | null; }

export interface WatchlistItem {
  ticker: string;
  added_at: string;
}

export interface ActionResults {
  trades: Array<{ ticker: string; side: "buy" | "sell"; quantity: number; status: "filled" | "rejected"; price: number | null; error: string | null }>;
  watchlist_changes: Array<{ ticker: string; action: "add" | "remove"; status: "applied" | "noop" | "rejected"; error: string | null }>;
}
export interface ChatResponse { message: string; actions: ActionResults; portfolio: PortfolioResponse; }
export interface ChatHistoryMessage { id: string; role: "user" | "assistant"; content: string; actions: ActionResults | null; created_at: string; }
export interface ResetResponse { ok: true; portfolio: PortfolioResponse; watchlist: WatchlistItem[]; }
