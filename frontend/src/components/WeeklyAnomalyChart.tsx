import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { WeekScore } from "../api/types";

/** Weekly anomaly scores; flagged weeks (Isolation Forest top 5%) in red. */
export const WeeklyAnomalyChart = ({ weeks }: { weeks: WeekScore[] }) => (
  <ResponsiveContainer width="100%" height={200}>
    <BarChart data={weeks} margin={{ left: 10, right: 10 }}>
      <CartesianGrid strokeDasharray="3 3" />
      <XAxis dataKey="week_start" minTickGap={40} />
      <YAxis domain={[0, 1]} width={40} />
      <Tooltip formatter={(v: number, _n, p) => [v.toFixed(2), p.payload.is_flagged ? "anomaly (FLAGGED)" : "anomaly"]} />
      <ReferenceLine y={0.5} stroke="#73849f" strokeDasharray="4 4" />
      <Bar dataKey="anomaly_score" name="Anomaly">
        {weeks.map((w) => (
          <Cell key={w.week_start} fill={w.is_flagged ? "#ff304f" : "#34496b"} />
        ))}
      </Bar>
    </BarChart>
  </ResponsiveContainer>
);
