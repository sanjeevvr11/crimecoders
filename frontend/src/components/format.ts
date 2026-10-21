export const inr = (n: number | null | undefined) =>
  n == null ? "—" : `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
export const pct = (n: number | null | undefined, digits = 0) => (n == null ? "—" : `${(n * 100).toFixed(digits)}%`);
export const num = (n: number | null | undefined, digits = 0) =>
  n == null ? "—" : n.toLocaleString("en-IN", { maximumFractionDigits: digits });
export const score = (n: number | null | undefined) => (n == null ? "—" : n.toFixed(1));
