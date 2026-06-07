import { ReactNode } from 'react'
import { Loader2, AlertCircle, InboxIcon } from 'lucide-react'
import { cn, CATEGORY_COLORS, SOURCE_LABELS } from '@/lib/utils'
import type { ExpenseCategory, ExpenseSource } from '@/types'

// ── DashboardCard ─────────────────────────────────────────────────────────────
interface DashboardCardProps {
  title: string
  value: string
  sub?: string
  icon: ReactNode
  trend?: number   // positive = green, negative = red
  iconBg?: string
}
export function DashboardCard({
  title, value, sub, icon, trend, iconBg = 'bg-green-100'
}: DashboardCardProps) {
  return (
    <div className="card p-5 flex items-start gap-4">
      <div className={cn('w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0', iconBg)}>
        {icon}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">{title}</p>
        <p className="text-2xl font-bold text-slate-800 mt-0.5 truncate">{value}</p>
        {(sub || trend !== undefined) && (
          <p className={cn('text-xs mt-1', trend !== undefined && trend >= 0 ? 'text-green-600' : 'text-red-500')}>
            {trend !== undefined
              ? `${trend >= 0 ? '↑' : '↓'} ${Math.abs(trend)}% vs last month`
              : sub}
          </p>
        )}
      </div>
    </div>
  )
}

// ── CategoryBadge ─────────────────────────────────────────────────────────────
export function CategoryBadge({ category }: { category: ExpenseCategory }) {
  return (
    <span className={cn('badge', CATEGORY_COLORS[category])}>
      {category}
    </span>
  )
}

// ── SourceBadge ───────────────────────────────────────────────────────────────
export function SourceBadge({ source }: { source: ExpenseSource }) {
  const { label, class: cls } = SOURCE_LABELS[source]
  return <span className={cn('badge', cls)}>{label}</span>
}

// ── ConfidenceBadge ───────────────────────────────────────────────────────────
export function ConfidenceBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100)
  const cls = pct >= 85 ? 'bg-green-100 text-green-700'
            : pct >= 60 ? 'bg-yellow-100 text-yellow-700'
            : 'bg-red-100 text-red-700'
  return <span className={cn('badge font-mono', cls)}>{pct}%</span>
}

// ── Loading ───────────────────────────────────────────────────────────────────
export function LoadingSpinner({ className }: { className?: string }) {
  return <Loader2 className={cn('animate-spin text-green-600', className)} />
}

export function PageLoader() {
  return (
    <div className="flex items-center justify-center py-20">
      <LoadingSpinner className="w-8 h-8" />
    </div>
  )
}

// ── Error state ───────────────────────────────────────────────────────────────
export function ErrorState({ message = 'Something went wrong' }: { message?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
      <AlertCircle className="w-10 h-10 text-red-400" />
      <p className="text-slate-600 text-sm">{message}</p>
    </div>
  )
}

// ── Empty state ───────────────────────────────────────────────────────────────
export function EmptyState({ message = 'No data yet' }: { message?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
      <InboxIcon className="w-10 h-10 text-slate-300" />
      <p className="text-slate-500 text-sm">{message}</p>
    </div>
  )
}

// ── Section heading ───────────────────────────────────────────────────────────
export function SectionTitle({ children }: { children: ReactNode }) {
  return <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wide mb-4">{children}</h2>
}
