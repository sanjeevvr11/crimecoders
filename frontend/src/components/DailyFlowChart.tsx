import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { DailyFlow } from "../api/types";
import { inr } from "./format";

export const DailyFlowChart = ({ daily }: { daily: DailyFlow[] }) => (
  <ResponsiveContainer width="100%" height={240}>
    <BarChart data={daily} margin={{ left: 10, right: 10 }}>
      <CartesianGrid strokeDasharray="3 3" />
      <XAxis dataKey="date" minTickGap={40} />
      <YAxis tickFormatter={(v) => `${(v / 1e5).toFixed(0)}L`} width={50} />
      <Tooltip formatter={(v: number) => inr(v)} />
      <Legend />
      <Bar dataKey="cr_amount" name="Credits" fill="#4d83ff" />
      <Bar dataKey="dr_amount" name="Debits" fill="#8857ff" />
    </BarChart>
  </ResponsiveContainer>
);
