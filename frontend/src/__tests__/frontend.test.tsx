import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TradeBar from "@/components/TradeBar";
import ChatPanel from "@/components/ChatPanel";
import Watchlist from "@/components/Watchlist";

const mocks = vi.hoisted(() => ({ trade: vi.fn(), chat: vi.fn(), history: vi.fn(), watchlist: vi.fn(), add: vi.fn(), remove: vi.fn() }));
vi.mock("@/lib/api", () => ({ api: { trade: mocks.trade, chat: mocks.chat, getChatHistory: mocks.history, getWatchlist: mocks.watchlist, addTicker: mocks.add, removeTicker: mocks.remove }, ApiError: class ApiError extends Error {} }));
vi.mock("recharts", () => ({ LineChart: ({ children }: { children: React.ReactNode }) => <svg>{children}</svg>, Line: () => null, YAxis: () => null }));

beforeEach(() => { vi.clearAllMocks(); mocks.history.mockResolvedValue([]); mocks.watchlist.mockResolvedValue([]); });
describe("contract UI", () => {
  it("submits a fractional trade using the contract envelope", async () => {
    mocks.trade.mockResolvedValue({ trade: { id: "1", ticker: "AAPL", side: "buy", quantity: .25, price: 190.12, executed_at: "2026-01-01T00:00:00Z" }, cash_balance: 9952.47, position: { ticker: "AAPL", quantity: .25, avg_cost: 190.12 } });
    const refreshed = vi.fn(); render(<TradeBar onTradeExecuted={refreshed}/>);
    fireEvent.change(screen.getByPlaceholderText("Ticker"), { target: { value: "aapl" } }); fireEvent.change(screen.getByPlaceholderText("Qty"), { target: { value: "0.25" } }); fireEvent.click(screen.getByText("BUY"));
    await waitFor(() => expect(mocks.trade).toHaveBeenCalledWith({ ticker: "AAPL", quantity: .25, side: "buy" }));
    expect(await screen.findByText("BUY 0.25 AAPL @ $190.12")).toBeInTheDocument(); expect(refreshed).toHaveBeenCalled();
  });
  it("hydrates chat history and displays filled and rejected action chips", async () => {
    mocks.history.mockResolvedValue([{ id: "1", role: "assistant", content: "Ready", actions: { trades: [{ ticker: "AAPL", side: "buy", quantity: 1, status: "filled", price: 190, error: null }], watchlist_changes: [{ ticker: "BAD", action: "add", status: "rejected", error: "unknown_ticker" }] }, created_at: "2026-01-01T00:00:00Z" }]);
    render(<ChatPanel/>); expect(await screen.findByText("Ready")).toBeInTheDocument(); expect(screen.getByText("Bought 1 AAPL @ $190.00")).toBeInTheDocument(); expect(screen.getByText("BAD: unknown_ticker")).toBeInTheDocument();
  });
  it("labels watchlist movement as session change", async () => {
    mocks.watchlist.mockResolvedValue([{ ticker: "AAPL", added_at: "2026-01-01T00:00:00Z" }]);
    render(<Watchlist prices={{ AAPL: { ticker: "AAPL", price: 110, previous_price: 109, timestamp: "2026-01-01T00:00:01Z", direction: "up" } }} priceHistory={{ AAPL: [{ price: 100, time: "2026-01-01T00:00:00Z" }, { price: 110, time: "2026-01-01T00:00:01Z" }] }} selectedTicker={null} onSelectTicker={vi.fn()}/>);
    expect(await screen.findByText("AAPL")).toBeInTheDocument(); expect(screen.getByText("Session%")).toBeInTheDocument(); expect(screen.getByText("+10.00%")).toBeInTheDocument();
  });
});
