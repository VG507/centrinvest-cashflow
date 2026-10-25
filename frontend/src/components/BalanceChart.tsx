import { CartesianGrid, ComposedChart, Line, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { dateLabel, fullDate, rub, shortRub } from '../lib/cashflow';

interface Props {
  data: { date: string; actual: number | null; forecast: number | null }[];
  cutoff: string;
  gaps: { from: string; to: string }[];
}
export default function BalanceChart({ data, cutoff, gaps }: Props) {
  return <ResponsiveContainer width="100%" height="100%"><ComposedChart data={data} margin={{ top: 12, right: 12, bottom: 12, left: 5 }} accessibilityLayer>
    <CartesianGrid strokeDasharray="3 5" vertical={false} stroke="#e5eaf0" />
    <XAxis dataKey="date" tickFormatter={dateLabel} minTickGap={40} tick={{ fill: '#61717a', fontSize: 12 }} axisLine={false} tickLine={false} dy={10} />
    <YAxis tickFormatter={shortRub} width={82} tick={{ fill: '#61717a', fontSize: 11 }} axisLine={false} tickLine={false} domain={['auto', 'auto']} />
    <Tooltip labelFormatter={value => fullDate(String(value))} formatter={(value, name) => [rub(Number(value)), name === 'actual' ? 'Факт' : 'Прогноз']} contentStyle={{ borderRadius: 10, border: '1px solid #dce3e7', fontSize: 14 }} />
    {gaps.map(g => <ReferenceArea key={g.from} x1={g.from} x2={g.to} fill="#b54a38" fillOpacity={0.07} />)}
    <ReferenceLine y={0} stroke="#b54a38" strokeDasharray="5 4" />
    <ReferenceLine x={cutoff} stroke="#9aa9b3" strokeDasharray="3 4" />
    <Line type="linear" dataKey="actual" stroke="#408578" strokeWidth={2.5} dot={false} isAnimationActive={false} connectNulls={false} />
    <Line type="linear" dataKey="forecast" stroke="#315acb" strokeWidth={2.5} strokeDasharray="6 4" dot={false} isAnimationActive={false} connectNulls={false} />
  </ComposedChart></ResponsiveContainer>;
}
