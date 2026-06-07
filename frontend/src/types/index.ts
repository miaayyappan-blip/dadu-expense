// ── Enums ─────────────────────────────────────────────────────────────────────
export type ExpenseCategory =
  | 'Food' | 'Transport' | 'Shopping' | 'Entertainment'
  | 'Health' | 'Utilities' | 'Education' | 'Travel' | 'Other'

export type ExpenseSource = 'VOICE' | 'OCR' | 'MANUAL'

// ── Auth ──────────────────────────────────────────────────────────────────────
export interface User {
  id: number
  email: string
  full_name: string
  is_active: boolean
  created_at: string
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

// ── Expense ───────────────────────────────────────────────────────────────────
export interface Expense {
  id: number
  user_id: number
  amount: number
  category: ExpenseCategory
  description: string
  merchant: string | null
  source: ExpenseSource
  date: string
  confidence: number | null
  created_at: string
  updated_at: string
}

export interface ExpenseCreateRequest {
  amount: number
  category: ExpenseCategory
  description: string
  merchant?: string
  date: string
  source?: ExpenseSource
}

export interface ExpenseUpdateRequest {
  amount?: number
  category?: ExpenseCategory
  description?: string
  merchant?: string
  date?: string
}

export interface ExpenseListResponse {
  items: Expense[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface ExpenseFilters {
  category?: ExpenseCategory
  source?: ExpenseSource
  date_from?: string
  date_to?: string
  search?: string
  page?: number
  page_size?: number
}

// ── Dashboard ─────────────────────────────────────────────────────────────────
export interface CategoryBreakdown {
  category: ExpenseCategory
  total: number
  percentage: number
  count: number
}

export interface DailyTrend {
  date: string
  total: number
}

export interface DashboardMetrics {
  total_spend_all_time: number
  total_spend_this_month: number
  total_spend_last_month: number
  month_over_month_change: number
  total_expenses_count: number
  average_expense_amount: number
  category_breakdown: CategoryBreakdown[]
  daily_trend_30d: DailyTrend[]
  recent_expenses: Expense[]
}

// ── Budget ────────────────────────────────────────────────────────────────────
export interface Budget {
  id: number
  category: ExpenseCategory
  monthly_limit: number
  is_active: boolean
}

export interface BudgetStatus {
  budget: Budget
  spent_this_month: number
  percentage_used: number
  is_warning: boolean
  is_exceeded: boolean
  remaining: number
}

// ── Voice ─────────────────────────────────────────────────────────────────────
export interface VoiceExtractResponse {
  transcript: string
  language: string
  audio_duration_seconds: number | null
  amount: number | null
  category: ExpenseCategory | null
  description: string | null
  merchant: string | null
  date: string | null
  confidence: number
  missing_fields: string[]
  low_confidence_fields: string[]
  suggestions: string
  extraction_notes: string | null
  needs_review: boolean
  is_empty_audio: boolean
}

// ── OCR ───────────────────────────────────────────────────────────────────────
export interface OcrExtractResponse {
  raw_ocr_text: string
  ocr_line_count: number
  ocr_quality: 'high' | 'medium' | 'low'
  image_quality_score: number
  was_image_enhanced: boolean
  is_partial_receipt: boolean
  items_detected: number
  amount: number | null
  category: ExpenseCategory | null
  description: string | null
  merchant: string | null
  date: string | null
  confidence: number
  ocr_confidence_score: number
  extraction_score: number
  missing_fields: string[]
  low_confidence_fields: string[]
  suggestions: string
  extraction_notes: string | null
  amount_warning: string | null
  date_warning: string | null
  needs_review: boolean
  is_empty_image: boolean
}

// ── AI Assistant ──────────────────────────────────────────────────────────────
export interface AssistantResponse {
  answer: string
  data: Record<string, unknown> | null
  query_type: string
}

// ── API generic ───────────────────────────────────────────────────────────────
export interface ApiError {
  detail: string
  errors?: Array<{ field: string; message: string }>
}
