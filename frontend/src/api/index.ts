import api from './client'
import type {
  TokenResponse, User,
  Expense, ExpenseCreateRequest, ExpenseUpdateRequest,
  ExpenseListResponse, ExpenseFilters,
  DashboardMetrics, BudgetStatus,
  VoiceExtractResponse, OcrExtractResponse,
  AssistantResponse,
} from '@/types'

// ── Auth ──────────────────────────────────────────────────────────────────────
export const authApi = {
  register: (email: string, full_name: string, password: string) =>
    api.post<User>('/auth/register', { email, full_name, password }),

  login: (email: string, password: string) =>
    api.post<TokenResponse>('/auth/login', { email, password }),

  me: () => api.get<User>('/auth/me'),

  logout: () => api.post('/auth/logout'),
}

// ── Expenses ──────────────────────────────────────────────────────────────────
export const expensesApi = {
  list: (filters: ExpenseFilters = {}) =>
    api.get<ExpenseListResponse>('/expenses', { params: filters }),

  get: (id: number) =>
    api.get<Expense>(`/expenses/${id}`),

  create: (data: ExpenseCreateRequest) =>
    api.post<Expense>('/expenses', data),

  update: (id: number, data: ExpenseUpdateRequest) =>
    api.patch<Expense>(`/expenses/${id}`, data),

  delete: (id: number) =>
    api.delete(`/expenses/${id}`),
}

// ── Dashboard ─────────────────────────────────────────────────────────────────
export const dashboardApi = {
  getMetrics: () =>
    api.get<DashboardMetrics>('/dashboard'),

  getBudgetStatuses: () =>
    api.get<BudgetStatus[]>('/budgets/status'),
}

// ── Budgets ───────────────────────────────────────────────────────────────────
export const budgetsApi = {
  upsert: (category: string, monthly_limit: number) =>
    api.post<BudgetStatus>('/budgets', { category, monthly_limit }),

  delete: (category: string) =>
    api.delete(`/budgets/${category}`),
}

// ── Voice ─────────────────────────────────────────────────────────────────────
export const voiceApi = {
  process: (audioFile: File, language?: string) => {
    const form = new FormData()
    form.append('audio', audioFile)
    if (language) form.append('language', language)
    return api.post<VoiceExtractResponse>('/voice/process', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

  confirm: (data: {
    amount: number; category: string; description: string
    merchant?: string; date: string
    original_confidence: number; transcript: string
  }) => api.post<Expense>('/voice/confirm', data),
}

// ── OCR ───────────────────────────────────────────────────────────────────────
export const ocrApi = {
  process: (imageFile: File) => {
    const form = new FormData()
    form.append('image', imageFile)
    return api.post<OcrExtractResponse>('/ocr/process', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

  confirm: (data: {
    amount: number; category: string; description: string
    merchant?: string; date: string
    original_confidence: number; original_ocr_text: string
  }) => api.post<Expense>('/ocr/confirm', data),
}

// ── AI Assistant ──────────────────────────────────────────────────────────────
export const assistantApi = {
  query: (query: string) =>
    api.post<AssistantResponse>('/assistant/query', { query }),
}

// ── Export ────────────────────────────────────────────────────────────────────
export const exportApi = {
  csv: () =>
    api.get('/export/csv', { responseType: 'blob' }),

  pdf: () =>
    api.get('/export/pdf', { responseType: 'blob' }),
}
