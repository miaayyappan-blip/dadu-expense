import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Search, ChevronLeft, ChevronRight, Pencil, Trash2, X, Check } from 'lucide-react'
import { expensesApi } from '@/api'
import {
  PageLoader, ErrorState, EmptyState,
  CategoryBadge, SourceBadge,
} from '@/components/ui'
import {
  formatCurrency, formatDate, CATEGORIES, getErrorMessage, cn,
} from '@/lib/utils'
import type { Expense, ExpenseCategory, ExpenseSource } from '@/types'

export default function ExpensesPage() {
  const qc = useQueryClient()
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState<ExpenseCategory | ''>('')
  const [source, setSource] = useState<ExpenseSource | ''>('')
  const [page, setPage] = useState(1)
  const [editId, setEditId] = useState<number | null>(null)
  const [editForm, setEditForm] = useState<Partial<Expense>>({})
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [actionLoading, setActionLoading] = useState(false)

  const { data, isLoading, error } = useQuery({
    queryKey: ['expenses', search, category, source, page],
    queryFn: () => expensesApi.list({
      search: search || undefined,
      category: category || undefined,
      source: source || undefined,
      page,
      page_size: 15,
    }).then(r => r.data),
    placeholderData: (prev) => prev,
  })

  const startEdit = (expense: Expense) => {
    setEditId(expense.id)
    setEditForm({
      amount: expense.amount,
      category: expense.category,
      description: expense.description,
      merchant: expense.merchant ?? '',
      date: expense.date,
    })
  }

  const saveEdit = async () => {
    if (!editId) return
    setActionLoading(true)
    try {
      await expensesApi.update(editId, {
        amount: Number(editForm.amount),
        category: editForm.category,
        description: editForm.description,
        merchant: editForm.merchant || undefined,
        date: editForm.date,
      })
      qc.invalidateQueries({ queryKey: ['expenses'] })
      qc.invalidateQueries({ queryKey: ['dashboard'] })
      setEditId(null)
    } finally {
      setActionLoading(false)
    }
  }

  const confirmDelete = async () => {
    if (!deleteId) return
    setActionLoading(true)
    try {
      await expensesApi.delete(deleteId)
      qc.invalidateQueries({ queryKey: ['expenses'] })
      qc.invalidateQueries({ queryKey: ['dashboard'] })
      setDeleteId(null)
    } finally {
      setActionLoading(false)
    }
  }

  if (isLoading && !data) return <PageLoader />
  if (error) return <ErrorState message={getErrorMessage(error)} />

  return (
    <div className="max-w-5xl space-y-4">
      {/* Filters */}
      <div className="card p-4 flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-48">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            className="input-base pl-9"
            placeholder="Search expenses…"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1) }}
          />
        </div>
        <select
          className="input-base w-36"
          value={category}
          onChange={(e) => { setCategory(e.target.value as any); setPage(1) }}
        >
          <option value="">All Categories</option>
          {CATEGORIES.map(c => <option key={c}>{c}</option>)}
        </select>
        <select
          className="input-base w-32"
          value={source}
          onChange={(e) => { setSource(e.target.value as any); setPage(1) }}
        >
          <option value="">All Sources</option>
          <option value="MANUAL">Manual</option>
          <option value="VOICE">Voice</option>
          <option value="OCR">Receipt</option>
        </select>
        {(search || category || source) && (
          <button
            onClick={() => { setSearch(''); setCategory(''); setSource(''); setPage(1) }}
            className="btn-secondary flex items-center gap-1.5 text-xs"
          >
            <X className="w-3.5 h-3.5" /> Clear
          </button>
        )}
      </div>

      {/* Table */}
      <div className="card overflow-hidden">
        {!data?.items.length ? (
          <EmptyState message="No expenses match your filters" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50">
                  {['Date', 'Description', 'Category', 'Amount', 'Source', 'Actions'].map(h => (
                    <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {data.items.map((expense) => (
                  <tr key={expense.id} className="hover:bg-slate-50/50 transition-colors">
                    {editId === expense.id ? (
                      // ── Inline edit row ───────────────────────────────────
                      <>
                        <td className="px-4 py-2">
                          <input type="date" className="input-base text-xs w-32"
                            value={editForm.date ?? ''} onChange={e => setEditForm(f => ({ ...f, date: e.target.value }))} />
                        </td>
                        <td className="px-4 py-2 space-y-1">
                          <input className="input-base text-xs" placeholder="Description"
                            value={editForm.description ?? ''} onChange={e => setEditForm(f => ({ ...f, description: e.target.value }))} />
                          <input className="input-base text-xs" placeholder="Merchant"
                            value={editForm.merchant ?? ''} onChange={e => setEditForm(f => ({ ...f, merchant: e.target.value }))} />
                        </td>
                        <td className="px-4 py-2">
                          <select className="input-base text-xs w-28"
                            value={editForm.category} onChange={e => setEditForm(f => ({ ...f, category: e.target.value as ExpenseCategory }))}>
                            {CATEGORIES.map(c => <option key={c}>{c}</option>)}
                          </select>
                        </td>
                        <td className="px-4 py-2">
                          <input type="number" className="input-base text-xs w-24"
                            value={editForm.amount ?? ''} onChange={e => setEditForm(f => ({ ...f, amount: parseFloat(e.target.value) }))} />
                        </td>
                        <td className="px-4 py-2">
                          <SourceBadge source={expense.source} />
                        </td>
                        <td className="px-4 py-2">
                          <div className="flex gap-2">
                            <button onClick={saveEdit} disabled={actionLoading}
                              className="p-1.5 text-green-600 hover:bg-green-50 rounded-lg">
                              <Check className="w-4 h-4" />
                            </button>
                            <button onClick={() => setEditId(null)}
                              className="p-1.5 text-slate-400 hover:bg-slate-100 rounded-lg">
                              <X className="w-4 h-4" />
                            </button>
                          </div>
                        </td>
                      </>
                    ) : (
                      // ── Normal row ────────────────────────────────────────
                      <>
                        <td className="px-4 py-3 text-slate-500 whitespace-nowrap">
                          {formatDate(expense.date)}
                        </td>
                        <td className="px-4 py-3 max-w-xs">
                          <p className="font-medium text-slate-800 truncate">{expense.description}</p>
                          {expense.merchant && (
                            <p className="text-xs text-slate-400 truncate">{expense.merchant}</p>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <CategoryBadge category={expense.category} />
                        </td>
                        <td className="px-4 py-3 font-semibold font-mono text-slate-800 whitespace-nowrap">
                          {formatCurrency(expense.amount)}
                        </td>
                        <td className="px-4 py-3">
                          <SourceBadge source={expense.source} />
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex gap-1">
                            <button onClick={() => startEdit(expense)}
                              className="p-1.5 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors">
                              <Pencil className="w-3.5 h-3.5" />
                            </button>
                            <button onClick={() => setDeleteId(expense.id)}
                              className="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors">
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {data && data.total_pages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-slate-100">
            <p className="text-xs text-slate-500">
              Showing {(page - 1) * 15 + 1}–{Math.min(page * 15, data.total)} of {data.total}
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => setPage(p => p - 1)}
                disabled={page === 1}
                className="btn-secondary px-2 py-1.5 disabled:opacity-40"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="text-xs text-slate-600 px-2 py-1.5 font-medium">
                {page} / {data.total_pages}
              </span>
              <button
                onClick={() => setPage(p => p + 1)}
                disabled={page === data.total_pages}
                className="btn-secondary px-2 py-1.5 disabled:opacity-40"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Delete confirm modal */}
      {deleteId && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="card p-6 w-full max-w-sm shadow-xl">
            <h3 className="font-semibold text-slate-800 mb-2">Delete Expense?</h3>
            <p className="text-sm text-slate-500 mb-5">This action cannot be undone.</p>
            <div className="flex gap-3">
              <button onClick={() => setDeleteId(null)} className="btn-secondary flex-1">Cancel</button>
              <button
                onClick={confirmDelete}
                disabled={actionLoading}
                className="flex-1 bg-red-600 hover:bg-red-700 text-white font-medium px-4 py-2 rounded-lg text-sm transition-colors"
              >
                {actionLoading ? 'Deleting…' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
