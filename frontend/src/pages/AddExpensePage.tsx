import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import {
  Mic, Upload, CheckCircle, AlertTriangle, RefreshCw,
  FileText, Image,
} from 'lucide-react'
import { expensesApi, voiceApi, ocrApi } from '@/api'
import { LoadingSpinner, ConfidenceBadge } from '@/components/ui'
import { CATEGORIES, formatCurrency, getErrorMessage, today, cn } from '@/lib/utils'
import type { ExpenseCategory, VoiceExtractResponse, OcrExtractResponse } from '@/types'

type Tab = 'manual' | 'voice' | 'receipt'

export default function AddExpensePage() {
  const [tab, setTab] = useState<Tab>('manual')

  return (
    <div className="max-w-xl">
      {/* Tab bar */}
      <div className="flex bg-white border border-slate-200 rounded-xl p-1 mb-6 gap-1">
        {([
          { id: 'manual',  label: 'Manual',  icon: FileText },
          { id: 'voice',   label: 'Voice',   icon: Mic },
          { id: 'receipt', label: 'Receipt', icon: Image },
        ] as const).map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={cn(
              'flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-sm font-medium transition-all',
              tab === id
                ? 'bg-green-600 text-white shadow-sm'
                : 'text-slate-500 hover:text-slate-700 hover:bg-slate-50',
            )}
          >
            <Icon className="w-4 h-4" />
            {label}
          </button>
        ))}
      </div>

      <div className="card p-6">
        {tab === 'manual'  && <ManualTab />}
        {tab === 'voice'   && <VoiceTab />}
        {tab === 'receipt' && <ReceiptTab />}
      </div>
    </div>
  )
}

// ── Manual Tab ────────────────────────────────────────────────────────────────
function ManualTab() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [form, setForm] = useState({
    amount: '', category: 'Food' as ExpenseCategory,
    description: '', merchant: '', date: today(),
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const submit = async () => {
    if (!form.amount || !form.description) {
      setError('Amount and description are required')
      return
    }
    setLoading(true)
    setError('')
    try {
      await expensesApi.create({
        amount: parseFloat(form.amount),
        category: form.category,
        description: form.description,
        merchant: form.merchant || undefined,
        date: form.date,
        source: 'MANUAL',
      })
      qc.invalidateQueries({ queryKey: ['dashboard'] })
      qc.invalidateQueries({ queryKey: ['expenses'] })
      navigate('/expenses')
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-4">
      <h2 className="font-semibold text-slate-800">Add Expense Manually</h2>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="text-xs font-medium text-slate-600 block mb-1">Amount (₹) *</label>
          <input
            type="number"
            className="input-base"
            placeholder="0.00"
            value={form.amount}
            onChange={(e) => setForm(f => ({ ...f, amount: e.target.value }))}
          />
        </div>
        <div>
          <label className="text-xs font-medium text-slate-600 block mb-1">Date *</label>
          <input
            type="date"
            className="input-base"
            value={form.date}
            onChange={(e) => setForm(f => ({ ...f, date: e.target.value }))}
          />
        </div>
      </div>

      <div>
        <label className="text-xs font-medium text-slate-600 block mb-1">Category *</label>
        <select
          className="input-base"
          value={form.category}
          onChange={(e) => setForm(f => ({ ...f, category: e.target.value as ExpenseCategory }))}
        >
          {CATEGORIES.map(c => <option key={c}>{c}</option>)}
        </select>
      </div>

      <div>
        <label className="text-xs font-medium text-slate-600 block mb-1">Description *</label>
        <input
          className="input-base"
          placeholder="Lunch at office canteen"
          value={form.description}
          onChange={(e) => setForm(f => ({ ...f, description: e.target.value }))}
        />
      </div>

      <div>
        <label className="text-xs font-medium text-slate-600 block mb-1">Merchant (optional)</label>
        <input
          className="input-base"
          placeholder="Swiggy, Amazon…"
          value={form.merchant}
          onChange={(e) => setForm(f => ({ ...f, merchant: e.target.value }))}
        />
      </div>

      {error && <p className="text-sm text-red-600 bg-red-50 px-3 py-2 rounded-lg">{error}</p>}

      <button onClick={submit} disabled={loading} className="btn-primary w-full py-2.5">
        {loading ? <span className="flex items-center justify-center gap-2"><LoadingSpinner className="w-4 h-4" /> Saving…</span> : 'Save Expense'}
      </button>
    </div>
  )
}

// ── Voice Tab ─────────────────────────────────────────────────────────────────
function VoiceTab() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [isRecording, setIsRecording] = useState(false)

  const mediaRecorderRef = useRef<MediaRecorder | null>(null)

  const chunksRef = useRef<Blob[]>([])

  type Stage = 'upload' | 'processing' | 'review' | 'saving'
  const [stage, setStage] = useState<Stage>('upload')
  const [extracted, setExtracted] = useState<VoiceExtractResponse | null>(null)
  const [form, setForm] = useState<any>({})
  const [error, setError] = useState('')

  const processAudio = async (file: File) => {
    setStage('processing')
    setError('')
    try {
      const { data } = await voiceApi.process(file)
      setExtracted(data)
      setForm({
        amount: data.amount ?? '',
        category: data.category ?? 'Other',
        description: data.description ?? '',
        merchant: data.merchant ?? '',
        date: data.date ?? today(),
      })
      setStage('review')
    } catch (err) {
      setError(getErrorMessage(err))
      setStage('upload')
    }
  }
  const startRecording = async () => {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: true,
    })

    const recorder = new MediaRecorder(stream)

    chunksRef.current = []

    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        chunksRef.current.push(event.data)
      }
    }

    mediaRecorderRef.current = recorder

    recorder.start()

    setIsRecording(true)
  } catch (err) {
    setError('Could not access microphone')
  }
}
  const stopRecording = () => {
    const recorder = mediaRecorderRef.current

    if (!recorder) return

    recorder.onstop = async () => {
      const blob = new Blob(
        chunksRef.current,
        { type: 'audio/webm' }
      )

      const file = new File(
        [blob],
        'recording.webm',
        { type: 'audio/webm' }
      )

      await processAudio(file)
    }

    recorder.stop()

    setIsRecording(false)
  }

  const confirm = async () => {
    if (!form.amount || !form.description) {
      setError('Amount and description required')
      return
    }
    setStage('saving')
    try {
      await voiceApi.confirm({
        amount: parseFloat(form.amount),
        category: form.category,
        description: form.description,
        merchant: form.merchant || undefined,
        date: form.date,
        original_confidence: extracted?.confidence ?? 0,
        transcript: extracted?.transcript ?? '',
      })
      qc.invalidateQueries({ queryKey: ['dashboard'] })
      qc.invalidateQueries({ queryKey: ['expenses'] })
      navigate('/expenses')
    } catch (err) {
      setError(getErrorMessage(err))
      setStage('review')
    }
  }

  if (stage === 'upload') return (
    <div className="space-y-4">
      <h2 className="font-semibold text-slate-800">Voice Expense Entry</h2>
      <p className="text-sm text-slate-500">Record or upload audio describing your expense</p>

    <div className="flex gap-3">
      {!isRecording ? (
        <button
          onClick={startRecording}
          className="btn-primary flex-1 flex items-center justify-center gap-2"
        >
          <Mic className="w-4 h-4" />
          Start Recording
        </button>
      ) : (
        <button
          onClick={stopRecording}
          className="w-full bg-red-600 text-white rounded-lg py-2.5
                    flex items-center justify-center gap-2"
        >
          Stop Recording
        </button>
      )}
    </div>

      <button
        onClick={() => fileRef.current?.click()}
        className="w-full border-2 border-dashed border-slate-200 rounded-xl p-10
                   flex flex-col items-center gap-3 hover:border-green-400 hover:bg-green-50/50
                   transition-colors cursor-pointer"
      >
        <Mic className="w-8 h-8 text-slate-400" />
        <span className="text-sm font-medium text-slate-600">Or Upload Audio File</span>
        <span className="text-xs text-slate-400">mp3, wav, webm, m4a, ogg</span>
      </button>
      <input
        ref={fileRef}
        type="file"
        accept="audio/*"
        className="hidden"
        onChange={(e) => e.target.files?.[0] && processAudio(e.target.files[0])}
      />

      <div className="bg-slate-50 rounded-lg p-3">
        <p className="text-xs font-medium text-slate-600 mb-1">Try saying:</p>
        {[
          '"Spent 250 on lunch at canteen today"',
          '"Auto to office, 80 rupees"',
          '"Amazon order 1500 last Saturday"',
        ].map((ex) => (
          <p key={ex} className="text-xs text-slate-400 font-mono">{ex}</p>
        ))}
      </div>

      {error && <p className="text-sm text-red-600 bg-red-50 px-3 py-2 rounded-lg">{error}</p>}
    </div>
  )

  if (stage === 'processing') return (
    <div className="flex flex-col items-center gap-4 py-12">
      <LoadingSpinner className="w-8 h-8" />
      <p className="text-slate-600 text-sm">Transcribing and extracting…</p>
    </div>
  )

  if (stage === 'review' && extracted) return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold text-slate-800">Review Extracted Expense</h2>
        <ConfidenceBadge score={extracted.confidence} />
      </div>

      {extracted.transcript && (
        <div className="bg-slate-50 rounded-lg p-3">
          <p className="text-xs font-medium text-slate-500 mb-1">Transcript</p>
          <p className="text-sm text-slate-700 italic">"{extracted.transcript}"</p>
        </div>
      )}

      {(extracted.needs_review || extracted.missing_fields.length > 0) && (
        <div className="flex gap-2 bg-amber-50 border border-amber-100 rounded-lg p-3">
          <AlertTriangle className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" />
          <p className="text-xs text-amber-700">{extracted.suggestions}</p>
        </div>
      )}

      <ExtractedForm form={form} setForm={setForm} />

      {error && <p className="text-sm text-red-600 bg-red-50 px-3 py-2 rounded-lg">{error}</p>}

      <div className="flex gap-3">
        <button onClick={() => setStage('upload')} className="btn-secondary flex items-center gap-1.5">
          <RefreshCw className="w-3.5 h-3.5" /> Re-record
        </button>
        <button onClick={confirm} className="btn-primary flex-1 flex items-center justify-center gap-2">
          <CheckCircle className="w-4 h-4" /> Save Expense
        </button>
      </div>
    </div>
  )

  return (
    <div className="flex flex-col items-center gap-4 py-12">
      <LoadingSpinner className="w-8 h-8" />
      <p className="text-slate-600 text-sm">Saving…</p>
    </div>
  )
}

// ── Receipt Tab ───────────────────────────────────────────────────────────────
function ReceiptTab() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)

  type Stage = 'upload' | 'processing' | 'review' | 'saving'
  const [stage, setStage] = useState<Stage>('upload')
  const [extracted, setExtracted] = useState<OcrExtractResponse | null>(null)
  const [form, setForm] = useState<any>({})
  const [preview, setPreview] = useState<string | null>(null)
  const [error, setError] = useState('')

  const processImage = async (file: File) => {
    setPreview(URL.createObjectURL(file))
    setStage('processing')
    setError('')
    try {
      const { data } = await ocrApi.process(file)
      setExtracted(data)
      setForm({
        amount: data.amount ?? '',
        category: data.category ?? 'Other',
        description: data.description ?? '',
        merchant: data.merchant ?? '',
        date: data.date ?? today(),
      })
      setStage('review')
    } catch (err) {
      setError(getErrorMessage(err))
      setStage('upload')
    }
  }

  const confirm = async () => {
    if (!form.amount || !form.description) {
      setError('Amount and description required')
      return
    }
    setStage('saving')
    try {
      await ocrApi.confirm({
        amount: parseFloat(form.amount),
        category: form.category,
        description: form.description,
        merchant: form.merchant || undefined,
        date: form.date,
        original_confidence: extracted?.confidence ?? 0,
        original_ocr_text: extracted?.raw_ocr_text ?? '',
      })
      qc.invalidateQueries({ queryKey: ['dashboard'] })
      qc.invalidateQueries({ queryKey: ['expenses'] })
      navigate('/expenses')
    } catch (err) {
      setError(getErrorMessage(err))
      setStage('review')
    }
  }

  if (stage === 'upload') return (
    <div className="space-y-4">
      <h2 className="font-semibold text-slate-800">Receipt Scanner</h2>
      <p className="text-sm text-slate-500">Upload a photo of your receipt</p>

      <button
        onClick={() => fileRef.current?.click()}
        className="w-full border-2 border-dashed border-slate-200 rounded-xl p-10
                   flex flex-col items-center gap-3 hover:border-green-400 hover:bg-green-50/50
                   transition-colors cursor-pointer"
      >
        <Upload className="w-8 h-8 text-slate-400" />
        <span className="text-sm font-medium text-slate-600">Upload Receipt Image</span>
        <span className="text-xs text-slate-400">jpeg, png, webp — max 10MB</span>
      </button>
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => e.target.files?.[0] && processImage(e.target.files[0])}
      />
      {error && <p className="text-sm text-red-600 bg-red-50 px-3 py-2 rounded-lg">{error}</p>}
    </div>
  )

  if (stage === 'processing') return (
    <div className="flex flex-col items-center gap-4 py-12">
      {preview && (
        <img src={preview} alt="receipt" className="w-32 h-40 object-cover rounded-lg opacity-60" />
      )}
      <LoadingSpinner className="w-8 h-8" />
      <p className="text-slate-600 text-sm">Scanning receipt…</p>
      <p className="text-xs text-slate-400">This may take a few seconds</p>
    </div>
  )

  if (stage === 'review' && extracted) return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold text-slate-800">Review Receipt Data</h2>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400">OCR: {extracted.ocr_quality}</span>
          <ConfidenceBadge score={extracted.confidence} />
        </div>
      </div>

      {(extracted.needs_review || extracted.missing_fields.length > 0) && (
        <div className="flex gap-2 bg-amber-50 border border-amber-100 rounded-lg p-3">
          <AlertTriangle className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" />
          <p className="text-xs text-amber-700">{extracted.suggestions}</p>
        </div>
      )}

      {extracted.amount_warning && (
        <div className="bg-orange-50 border border-orange-100 rounded-lg p-3">
          <p className="text-xs text-orange-700">{extracted.amount_warning}</p>
        </div>
      )}

      <ExtractedForm form={form} setForm={setForm} />

      {error && <p className="text-sm text-red-600 bg-red-50 px-3 py-2 rounded-lg">{error}</p>}

      <div className="flex gap-3">
        <button onClick={() => setStage('upload')} className="btn-secondary flex items-center gap-1.5">
          <RefreshCw className="w-3.5 h-3.5" /> Re-scan
        </button>
        <button onClick={confirm} className="btn-primary flex-1 flex items-center justify-center gap-2">
          <CheckCircle className="w-4 h-4" /> Save Expense
        </button>
      </div>
    </div>
  )

  return (
    <div className="flex flex-col items-center gap-4 py-12">
      <LoadingSpinner className="w-8 h-8" />
      <p className="text-slate-600 text-sm">Saving…</p>
    </div>
  )
}

// ── Shared extracted fields form ──────────────────────────────────────────────
function ExtractedForm({ form, setForm }: { form: any; setForm: (f: any) => void }) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs font-medium text-slate-600 block mb-1">Amount (₹) *</label>
          <input
            type="number"
            className="input-base"
            value={form.amount}
            onChange={(e) => setForm((f: any) => ({ ...f, amount: e.target.value }))}
          />
        </div>
        <div>
          <label className="text-xs font-medium text-slate-600 block mb-1">Date *</label>
          <input
            type="date"
            className="input-base"
            value={form.date}
            onChange={(e) => setForm((f: any) => ({ ...f, date: e.target.value }))}
          />
        </div>
      </div>
      <div>
        <label className="text-xs font-medium text-slate-600 block mb-1">Category *</label>
        <select
          className="input-base"
          value={form.category}
          onChange={(e) => setForm((f: any) => ({ ...f, category: e.target.value }))}
        >
          {CATEGORIES.map(c => <option key={c}>{c}</option>)}
        </select>
      </div>
      <div>
        <label className="text-xs font-medium text-slate-600 block mb-1">Description *</label>
        <input
          className="input-base"
          value={form.description}
          onChange={(e) => setForm((f: any) => ({ ...f, description: e.target.value }))}
        />
      </div>
      <div>
        <label className="text-xs font-medium text-slate-600 block mb-1">Merchant</label>
        <input
          className="input-base"
          value={form.merchant}
          onChange={(e) => setForm((f: any) => ({ ...f, merchant: e.target.value }))}
        />
      </div>
    </div>
  )
}
