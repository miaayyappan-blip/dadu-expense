import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Plus, Trash2, Download, AlertTriangle, CheckCircle, AlertOctagon,
} from 'lucide-react'
import { dashboardApi, budgetsApi } from '@/api'
import { PageLoader, ErrorState, EmptyState } from '@/components/ui'
import { formatCurrency, CATEGORIES, getErrorMessage, cn } from '@/lib/utils'
import type { ExpenseCategory } from '@/types'

export default function BudgetsPage() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [newCategory, setNewCategory] = useState<ExpenseCategory>('Food')
  const [newLimit, setNewLimit] = useState('')
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState('')

  const { data: budgets, isLoading, error } = useQuery({
    queryKey: ['budgets'],
    queryFn: () => dashboardApi.getBudgetStatuses().then(r => r.data),
  })

  const saveBudget = async () => {
    if (!newLimit || parseFloat(newLimit) <= 0) {
      setFormError('Please enter a valid amount')
      return
    }
    setSaving(true)
    setFormError('')
    try {
      await budgetsApi.upsert(newCategory, parseFloat(newLimit))
      qc.invalidateQueries({ queryKey: ['budgets'] })
      setShowForm(false)
      setNewLimit('')
    } catch (err) {
      setFormError(getErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const deleteBudget = async (category: ExpenseCategory) => {
    try {
      await budgetsApi.delete(category)
      qc.invalidateQueries({ queryKey: ['budgets'] })
    } catch {}
  }


  if (isLoading) return <PageLoader />
  if (error) return <ErrorState message={getErrorMessage(error)} />

  return (
    <div className="max-w-2xl space-y-6">
      {/* Budgets header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-semibold text-slate-800">Monthly Budgets</h2>
          <p className="text-xs text-slate-500 mt-0.5">Set limits per category and track progress</p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="btn-primary flex items-center gap-2"
        >
          <Plus className="w-4 h-4" />
          New Budget
        </button>
      </div>

      {/* Add budget form */}
      {showForm && (
        <div className="card p-5 border-green-200 bg-green-50/30">
          <h3 className="font-medium text-slate-700 mb-4 text-sm">Create Budget</h3>
          <div className="flex gap-3 flex-wrap">
            <select
              className="input-base w-40"
              value={newCategory}
              onChange={(e) => setNewCategory(e.target.value as ExpenseCategory)}
            >
              {CATEGORIES.map(c => <option key={c}>{c}</option>)}
            </select>
            <div className="relative flex-1 min-w-36">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 text-sm">₹</span>
              <input
                type="number"
                className="input-base pl-7"
                placeholder="5000"
                value={newLimit}
                onChange={(e) => setNewLimit(e.target.value)}
              />
            </div>
            <div className="flex gap-2">
              <button onClick={saveBudget} disabled={saving} className="btn-primary">
                {saving ? 'Saving…' : 'Save'}
              </button>
              <button onClick={() => { setShowForm(false); setFormError('') }} className="btn-secondary">
                Cancel
              </button>
            </div>
          </div>
          {formError && <p className="text-xs text-red-600 mt-2">{formError}</p>}
        </div>
      )}

      {/* Budget cards */}
      {!budgets?.length ? (
        <div className="card">
          <EmptyState message="No budgets yet — create one to track your spending" />
        </div>
      ) : (
        <div className="space-y-3">
          {budgets.map((bs) => {
            const pct = bs.percentage_used
            const barColor = pct >= 100 ? 'bg-red-500' : pct >= 80 ? 'bg-amber-500' : 'bg-green-500'

            return (
              <div key={bs.budget.id} className="card p-5">
                <div className="flex items-start justify-between gap-4 mb-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-slate-800">{bs.budget.category}</span>
                      {bs.is_exceeded && (
                        <span className="badge bg-red-100 text-red-700 flex items-center gap-1">
                          <AlertOctagon className="w-3 h-3" /> Over budget
                        </span>
                      )}
                      {!bs.is_exceeded && bs.is_warning && (
                        <span className="badge bg-amber-100 text-amber-700 flex items-center gap-1">
                          <AlertTriangle className="w-3 h-3" /> 80% reached
                        </span>
                      )}
                      {!bs.is_warning && (
                        <span className="badge bg-green-100 text-green-700 flex items-center gap-1">
                          <CheckCircle className="w-3 h-3" /> On track
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-slate-500 mt-1">
                      {formatCurrency(bs.spent_this_month)} of {formatCurrency(bs.budget.monthly_limit)} this month
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className={cn(
                      'text-sm font-bold font-mono',
                      bs.is_exceeded ? 'text-red-600' : bs.is_warning ? 'text-amber-600' : 'text-slate-700'
                    )}>
                      {pct.toFixed(0)}%
                    </span>
                    <button
                      onClick={() => deleteBudget(bs.budget.category)}
                      className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                {/* Progress bar */}
                <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                  <div
                    className={cn('h-full rounded-full transition-all', barColor)}
                    style={{ width: `${Math.min(pct, 100)}%` }}
                  />
                </div>

                <div className="flex justify-between mt-2">
                  <span className="text-xs text-slate-400">
                    {formatCurrency(bs.remaining)} remaining
                  </span>
                  <span className="text-xs text-slate-400">
                    Limit: {formatCurrency(bs.budget.monthly_limit)}
                  </span>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Reports section */}
      <ExportSection />
    </div>
  )
}

function ExportSection() {
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo]     = useState('')
  const [exportError, setExportError] = useState('')
  const [exporting, setExporting] = useState<'csv' | 'pdf' | null>(null)

  const doExport = async (type: 'csv' | 'pdf') => {
    setExporting(type)
    setExportError('')
    try {
      const params = new URLSearchParams()
      if (dateFrom) params.set('date_from', dateFrom)
      if (dateTo)   params.set('date_to',   dateTo)
      const qs = params.toString() ? `?${params.toString()}` : ''

      const token = localStorage.getItem('access_token')
      const res = await fetch(`/api/v1/export/${type}${qs}`, {
        headers: { Authorization: `Bearer ${token}` },
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Export failed' }))
        throw new Error(err.detail)
      }

      const blob = await res.blob()
      const ext  = type === 'csv' ? 'csv' : 'pdf'
      const name = dateFrom && dateTo
        ? `expenses_${dateFrom}_to_${dateTo}.${ext}`
        : `expenses_all.${ext}`

      const url = URL.createObjectURL(blob)
      const a   = document.createElement('a')
      a.href     = url
      a.download = name
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (err: any) {
      setExportError(err.message ?? 'Export failed. Please try again.')
    } finally {
      setExporting(null)
    }
  }

  return (
    <div className="card p-5">
      <h2 className="font-semibold text-slate-800 mb-1">Export Reports</h2>
      <p className="text-xs text-slate-500 mb-4">Download your expense data as CSV or PDF</p>

      <div className="flex flex-wrap gap-3 mb-4">
        <div>
          <label className="text-xs font-medium text-slate-600 block mb-1">From (optional)</label>
          <input type="date" className="input-base w-36 text-sm" value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)} />
        </div>
        <div>
          <label className="text-xs font-medium text-slate-600 block mb-1">To (optional)</label>
          <input type="date" className="input-base w-36 text-sm" value={dateTo}
            onChange={(e) => setDateTo(e.target.value)} />
        </div>
        {(dateFrom || dateTo) && (
          <div className="flex items-end">
            <button onClick={() => { setDateFrom(''); setDateTo('') }}
              className="btn-secondary text-xs px-3 py-2">Clear</button>
          </div>
        )}
      </div>

      <div className="flex gap-3 flex-wrap">
        <button onClick={() => doExport('csv')} disabled={!!exporting}
          className="btn-secondary flex items-center gap-2">
          <Download className="w-4 h-4" />
          {exporting === 'csv' ? 'Exporting…' : 'Export CSV'}
        </button>
        <button onClick={() => doExport('pdf')} disabled={!!exporting}
          className="btn-secondary flex items-center gap-2">
          <Download className="w-4 h-4" />
          {exporting === 'pdf' ? 'Exporting…' : 'Export PDF'}
        </button>
      </div>

      {exportError && (
        <p className="text-xs text-red-600 mt-3 bg-red-50 px-3 py-2 rounded-lg">{exportError}</p>
      )}

      <div className="mt-3 grid grid-cols-2 gap-3 text-xs text-slate-400">
        <p>📄 <b>CSV</b> — all fields, Excel-compatible, includes summary stats</p>
        <p>📊 <b>PDF</b> — formatted report with category breakdown + page numbers</p>
      </div>
    </div>
  )
}
