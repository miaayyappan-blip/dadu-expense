import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from 'recharts'
import {
  Wallet, TrendingUp, TrendingDown, Receipt, Bot, Send,
} from 'lucide-react'
import { dashboardApi, assistantApi } from '@/api'
import {
  DashboardCard, PageLoader, ErrorState, CategoryBadge,
  SectionTitle, LoadingSpinner,
} from '@/components/ui'
import {
  formatCurrency, formatShortDate, formatDate, CHART_COLORS, getErrorMessage,
} from '@/lib/utils'

export default function DashboardPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard'],
    queryFn: () => dashboardApi.getMetrics().then((r) => r.data),
  })

  const [query, setQuery] = useState('')
  const [answer, setAnswer] = useState('')
  const [aiLoading, setAiLoading] = useState(false)

  const askAssistant = async () => {
    if (!query.trim()) return
    setAiLoading(true)
    setAnswer('')
    try {
      const { data: res } = await assistantApi.query(query)
      setAnswer(res.answer)
    } catch (err) {
      setAnswer('Sorry, I could not process that. Try again.')
    } finally {
      setAiLoading(false)
    }
  }

  if (isLoading) return <PageLoader />
  if (error || !data) return <ErrorState message={getErrorMessage(error)} />

  const mom = data.month_over_month_change

  // Sample AI insights derived from data
  const insights = generateInsights(data)

  return (
    <div className="space-y-6 max-w-6xl">
      {/* Summary cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <DashboardCard
          title="Total Spent"
          value={formatCurrency(data.total_spend_all_time)}
          sub={`${data.total_expenses_count} transactions`}
          icon={<Wallet className="w-5 h-5 text-green-700" />}
        />
        <DashboardCard
          title="This Month"
          value={formatCurrency(data.total_spend_this_month)}
          trend={mom}
          icon={mom >= 0
            ? <TrendingUp className="w-5 h-5 text-orange-600" />
            : <TrendingDown className="w-5 h-5 text-green-600" />}
          iconBg={mom >= 0 ? 'bg-orange-100' : 'bg-green-100'}
        />
        <DashboardCard
          title="Last Month"
          value={formatCurrency(data.total_spend_last_month)}
          sub="Previous period"
          icon={<Receipt className="w-5 h-5 text-blue-600" />}
          iconBg="bg-blue-100"
        />
        <DashboardCard
          title="Avg per Expense"
          value={formatCurrency(data.average_expense_amount)}
          sub="Per transaction"
          icon={<TrendingUp className="w-5 h-5 text-purple-600" />}
          iconBg="bg-purple-100"
        />
      </div>

      {/* Charts row */}
      <div className="grid lg:grid-cols-3 gap-4">
        {/* Line chart */}
        <div className="card p-5 lg:col-span-2">
          <SectionTitle>Daily Spending — Last 30 Days</SectionTitle>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={data.daily_trend_30d}>
              <XAxis
                dataKey="date"
                tickFormatter={formatShortDate}
                tick={{ fontSize: 11, fill: '#94a3b8' }}
                tickLine={false}
                axisLine={false}
                interval={6}
              />
              <YAxis
                tickFormatter={(v) => `₹${(v / 1000).toFixed(0)}k`}
                tick={{ fontSize: 11, fill: '#94a3b8' }}
                tickLine={false}
                axisLine={false}
                width={45}
              />
              <Tooltip
                formatter={(v: number) => [formatCurrency(v), 'Spent']}
                labelFormatter={formatDate}
                contentStyle={{
                  border: '1px solid #e2e8f0', borderRadius: 8,
                  fontSize: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
                }}
              />
              <Line
                type="monotone"
                dataKey="total"
                stroke="#16a34a"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, strokeWidth: 0 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Pie chart */}
        <div className="card p-5">
          <SectionTitle>Category Breakdown</SectionTitle>
          {data.category_breakdown.length === 0 ? (
            <div className="flex items-center justify-center h-48 text-slate-400 text-sm">
              No data yet
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie
                  data={data.category_breakdown}
                  dataKey="total"
                  nameKey="category"
                  cx="50%"
                  cy="50%"
                  innerRadius={55}
                  outerRadius={85}
                  paddingAngle={2}
                >
                  {data.category_breakdown.map((_, i) => (
                    <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(v: number) => formatCurrency(v)}
                  contentStyle={{ border: '1px solid #e2e8f0', borderRadius: 8, fontSize: 12 }}
                />
                <Legend
                  iconType="circle"
                  iconSize={8}
                  formatter={(v) => <span style={{ fontSize: 11, color: '#64748b' }}>{v}</span>}
                />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Bottom row */}
      <div className="grid lg:grid-cols-3 gap-4">
        {/* Recent expenses */}
        <div className="card p-5 lg:col-span-2">
          <SectionTitle>Recent Expenses</SectionTitle>
          {data.recent_expenses.length === 0 ? (
            <p className="text-slate-400 text-sm py-8 text-center">No expenses yet</p>
          ) : (
            <div className="divide-y divide-slate-100">
              {data.recent_expenses.map((e) => (
                <div key={e.id} className="flex items-center gap-3 py-3">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-800 truncate">{e.description}</p>
                    <p className="text-xs text-slate-400">{formatDate(e.date)} · {e.merchant ?? e.category}</p>
                  </div>
                  <CategoryBadge category={e.category} />
                  <span className="text-sm font-semibold text-slate-800 font-mono">
                    {formatCurrency(e.amount)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* AI panel */}
        <div className="space-y-4">
          {/* Insights */}
          <div className="card p-5">
            <div className="flex items-center gap-2 mb-3">
              <Bot className="w-4 h-4 text-green-600" />
              <SectionTitle>AI Insights</SectionTitle>
            </div>
            <ul className="space-y-2">
              {insights.map((ins, i) => (
                <li key={i} className="flex gap-2 text-xs text-slate-600">
                  <span className="text-green-500 mt-0.5 flex-shrink-0">•</span>
                  {ins}
                </li>
              ))}
            </ul>
          </div>

          {/* AI Assistant */}
          <div className="card p-5">
            <div className="flex items-center gap-2 mb-3">
              <Bot className="w-4 h-4 text-green-600" />
              <SectionTitle>Ask Assistant</SectionTitle>
            </div>
            <div className="flex gap-2">
              <input
                className="input-base flex-1 text-xs"
                placeholder="How much on food this month?"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && askAssistant()}
              />
              <button
                onClick={askAssistant}
                disabled={aiLoading || !query.trim()}
                className="btn-primary px-3"
              >
                {aiLoading
                  ? <LoadingSpinner className="w-3.5 h-3.5" />
                  : <Send className="w-3.5 h-3.5" />}
              </button>
            </div>
            {answer && (
              <div className="mt-3 p-3 bg-green-50 rounded-lg text-xs text-slate-700 leading-relaxed border border-green-100">
                {answer}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function generateInsights(data: ReturnType<typeof dashboardApi.getMetrics> extends Promise<infer T> ? T extends { data: infer D } ? D : never : never): string[] {
  const insights: string[] = []
  const top = data.category_breakdown[0]
  if (top) insights.push(`${top.category} is your top category at ${top.percentage}% of spending`)
  const mom = data.month_over_month_change
  if (mom > 0) insights.push(`Spending up ${mom}% vs last month`)
  else if (mom < 0) insights.push(`Spending down ${Math.abs(mom)}% vs last month — great job!`)
  if (data.total_expenses_count > 0)
    insights.push(`${data.total_expenses_count} expenses tracked, avg ${Math.round(data.average_expense_amount)} per transaction`)
  return insights.slice(0, 3)
}
