import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'
import type { ExpenseCategory, ExpenseSource } from '@/types'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency', currency: 'INR', maximumFractionDigits: 0,
  }).format(amount)
}

export function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-IN', {
    day: 'numeric', month: 'short', year: 'numeric',
  })
}

export function formatShortDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-IN', {
    day: 'numeric', month: 'short',
  })
}

export function today(): string {
  return new Date().toISOString().split('T')[0]
}

// Category → Tailwind color classes
export const CATEGORY_COLORS: Record<ExpenseCategory, string> = {
  Food:          'bg-orange-100 text-orange-700',
  Transport:     'bg-blue-100 text-blue-700',
  Shopping:      'bg-purple-100 text-purple-700',
  Entertainment: 'bg-pink-100 text-pink-700',
  Health:        'bg-red-100 text-red-700',
  Utilities:     'bg-yellow-100 text-yellow-700',
  Education:     'bg-cyan-100 text-cyan-700',
  Travel:        'bg-indigo-100 text-indigo-700',
  Other:         'bg-slate-100 text-slate-700',
}

// Recharts chart colors
export const CHART_COLORS = [
  '#16a34a', '#3b82f6', '#f59e0b', '#ef4444',
  '#8b5cf6', '#ec4899', '#06b6d4', '#f97316', '#64748b',
]

export const SOURCE_LABELS: Record<ExpenseSource, { label: string; class: string }> = {
  VOICE:  { label: 'Voice',   class: 'bg-violet-100 text-violet-700' },
  OCR:    { label: 'Receipt', class: 'bg-blue-100 text-blue-700' },
  MANUAL: { label: 'Manual',  class: 'bg-slate-100 text-slate-600' },
}

export const CATEGORIES: ExpenseCategory[] = [
  'Food', 'Transport', 'Shopping', 'Entertainment',
  'Health', 'Utilities', 'Education', 'Travel', 'Other',
]

export function getErrorMessage(error: unknown): string {
  const err = error as any
  return err?.response?.data?.detail ?? err?.message ?? 'Something went wrong'
}
