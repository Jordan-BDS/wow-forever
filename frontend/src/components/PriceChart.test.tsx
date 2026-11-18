import { render, screen, within } from "@testing-library/react";
import type { AuctionRoundTrip, AuctionTrade } from "@/api/auctions";
import { PriceHistory, TradeRecap } from "./PriceChart";

const at = (hour: number) => new Date(Date.UTC(2026, 10, 18, hour)).toISOString();
const points = [0, 6, 12, 18].map((hour, i) => ({
  at: at(hour),
  price: 100 + i * 20,
  listed: 5,
  by: "Thrall",
}));
const trade = (id: number, kind: "buy" | "sell", hour: number, quantity: number | null, total: number) =>
  ({
    id,
    at: at(hour),
    kind,
    source: "mail",
    quantity,
    price: quantity ? Math.floor(total / quantity) : null,
    total,
    fee: kind === "sell" ? 30 : 0,
  }) satisfies AuctionTrade;
const trades = [
  trade(1, "buy", 3, 3, 300),
  trade(2, "sell", 9, 3, 600),
  trade(3, "sell", 10, null, 900), // quantité inconnue : pas de prix à l'unité, donc pas sur la courbe
  trade(4, "buy", 23, 1, 80), // après le dernier scan : hors de la courbe
];
const trips: AuctionRoundTrip[] = [
  {
    sale: 2,
    bought_at: at(3),
    sold_at: at(9),
    quantity: 3,
    sold: 3,
    buy_price: 100,
    sell_price: 200,
    cost: 300,
    fee: 30,
    revenue: 570,
    profit: 270,
    margin: 90,
    seconds: 6 * 3600,
  },
];

describe("PriceHistory", () => {
  it("marks my purchases and sales on the price curve", () => {
    const { container } = render(<PriceHistory points={points} trades={trades} trips={trips} />);
    const labels = [...container.querySelectorAll("path > title")].map((title) => title.textContent);
    expect(labels).toHaveLength(2);
    expect(labels[0]).toMatch(/^Achat du .* : 3 × 1 pa, total 3 pa$/);
    expect(labels[1]).toMatch(/^Vente du .* : 3 × 2 pa, total 6 pa$/);
    // Le trait de la revente, de l'achat à la vente.
    expect(container.querySelectorAll('line[stroke-dasharray="2 3"]')).toHaveLength(1);
    expect(screen.getByText(/mes achats/)).toBeInTheDocument();
  });

  it("draws nothing more without trades", () => {
    const { container } = render(<PriceHistory points={points} />);
    expect(container.querySelectorAll("path > title")).toHaveLength(0);
    expect(screen.queryByText(/mes achats/)).not.toBeInTheDocument();
  });
});

describe("TradeRecap", () => {
  it("sums up my round trips and lists every trade", () => {
    render(
      <TradeRecap
        trades={trades}
        trips={trips}
        summary={{ trips: 1, profit: 270, stock: 1, stock_cost: 80 }}
      />,
    );
    expect(screen.getByText("+2 pa 70 pc")).toBeInTheDocument();
    expect(screen.getByText("payé 80 pc")).toBeInTheDocument();
    const [roundTrips, all] = screen.getAllByRole("table", { hidden: true });
    const row = within(roundTrips).getAllByRole("row")[1];
    expect(row).toHaveTextContent("+2 pa 70 pc (+90 %)");
    expect(row).toHaveTextContent("6 h");
    expect(within(all).getAllByRole("row", { hidden: true })).toHaveLength(5);
  });
});
