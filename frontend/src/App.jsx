import {
  BookOpen,
  CheckCircle2,
  CircleAlert,
  Eye,
  FilePlus2,
  FolderOpen,
  FolderPlus,
  Gauge,
  Image,
  LibraryBig,
  ListTree,
  Loader2,
  Play,
  RotateCcw,
  Settings2,
  Square,
  TextCursorInput,
  Trash2,
  Type,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

const defaultConfig = {
  inputs: [],
  outputDir: '',
  encoding: '自动识别',
  title: '',
  author: '',
  coverImage: '',
  font: '',
  recursive: true,
  overwrite: false,
  keepTocText: false,
  allowWeakTitle: false,
  maxTitleLength: 90,
  maxCharsPerXhtml: 240000,
  previewLimit: 80,
  chapterRegex: '',
  language: 'zh-CN',
  publisher: '',
  description: '',
}

const defaultStats = {
  total: 0,
  current: 0,
  ok: 0,
  failed: 0,
  preview: 0,
}

function apiReady() {
  return Boolean(window.pywebview?.api)
}

async function callApi(method, ...args) {
  if (!apiReady()) {
    throw new Error('桌面后端尚未就绪。')
  }
  return window.pywebview.api[method](...args)
}

function mergePaths(current, incoming) {
  const seen = new Set(current)
  const merged = [...current]
  for (const item of incoming || []) {
    if (!seen.has(item)) {
      seen.add(item)
      merged.push(item)
    }
  }
  return merged
}

function shortPath(path) {
  if (!path) return ''
  const normalized = path.replaceAll('\\', '/')
  const parts = normalized.split('/')
  if (parts.length <= 3) return path
  return `${parts[0]}/.../${parts.slice(-2).join('/')}`
}

export default function App() {
  const [ready, setReady] = useState(apiReady())
  const [encodingOptions, setEncodingOptions] = useState(['自动识别'])
  const [config, setConfig] = useState(defaultConfig)
  const [logs, setLogs] = useState([])
  const [results, setResults] = useState([])
  const [stats, setStats] = useState(defaultStats)
  const [running, setRunning] = useState(false)
  const [status, setStatus] = useState('待命')
  const [lastOutputDir, setLastOutputDir] = useState('')
  const logEndRef = useRef(null)

  const progress = stats.total ? Math.min(100, Math.round((stats.current / stats.total) * 100)) : 0
  const currentFile = useMemo(() => {
    const last = logs.findLast?.((line) => line.startsWith('['))
    return last || ''
  }, [logs])

  useEffect(() => {
    const load = async () => {
      if (!apiReady()) return
      setReady(true)
      const state = await callApi('get_initial_state')
      setEncodingOptions(state.encodingOptions || ['自动识别'])
      setConfig((value) => ({ ...value, ...(state.defaults || {}) }))
    }

    if (apiReady()) {
      load()
    } else {
      window.addEventListener('pywebviewready', load, { once: true })
      return () => window.removeEventListener('pywebviewready', load)
    }
  }, [])

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [logs])

  useEffect(() => {
    if (!running) return undefined
    const timer = window.setInterval(async () => {
      try {
        const events = await callApi('poll_events')
        if (events?.length) {
          applyEvents(events)
        }
      } catch (error) {
        setStatus(error.message)
        setRunning(false)
      }
    }, 250)
    return () => window.clearInterval(timer)
  }, [running])

  const updateConfig = useCallback((key, value) => {
    setConfig((current) => ({ ...current, [key]: value }))
  }, [])

  const appendLog = useCallback((message) => {
    setLogs((current) => [...current, message])
  }, [])

  const applyEvents = useCallback((events) => {
    for (const event of events) {
      if (event.type === 'started') {
        setStats({ ...defaultStats, total: event.total || 0 })
        setStatus(event.preview ? '正在预览目录' : '正在转换 EPUB')
      }
      if (event.type === 'outputDir') {
        setLastOutputDir(event.path || '')
        setConfig((current) => ({ ...current, outputDir: event.path || current.outputDir }))
      }
      if (event.type === 'progress') {
        setStats((current) => ({
          ...current,
          current: event.current || 0,
          total: event.total || current.total,
        }))
      }
      if (event.type === 'result') {
        setResults((current) => [...current, event.result])
        setStats((current) => ({
          ...current,
          ok: current.ok + (event.result?.status === 'ok' ? 1 : 0),
          failed: current.failed + (event.result?.status === 'failed' ? 1 : 0),
          preview: current.preview + (event.result?.status === 'preview' ? 1 : 0),
        }))
      }
      if (event.type === 'log') {
        appendLog(event.message || '')
      }
      if (event.type === 'done') {
        const summary = event.summary || defaultStats
        setStats((current) => ({
          ...current,
          current: summary.total || current.current,
          total: summary.total || current.total,
          ok: summary.ok || 0,
          failed: summary.failed || 0,
          preview: summary.preview || 0,
        }))
        setStatus(`完成：成功 ${summary.ok || 0}，失败 ${summary.failed || 0}，预览 ${summary.preview || 0}`)
        setRunning(false)
      }
      if (event.type === 'error') {
        appendLog(event.detail || event.message || '任务失败')
        setStatus(event.message || '任务失败')
        setRunning(false)
      }
    }
  }, [appendLog])

  const addTxtFiles = async () => {
    const files = await callApi('choose_txt_files')
    updateConfig('inputs', mergePaths(config.inputs, files))
  }

  const addFolder = async () => {
    const folders = await callApi('choose_folder')
    updateConfig('inputs', mergePaths(config.inputs, folders))
  }

  const choosePath = async (method, key) => {
    const value = await callApi(method)
    if (value) updateConfig(key, value)
  }

  const removeInput = (index) => {
    updateConfig('inputs', config.inputs.filter((_, itemIndex) => itemIndex !== index))
  }

  const start = async (preview) => {
    setLogs([])
    setResults([])
    setStats(defaultStats)
    setStatus(preview ? '准备预览' : '准备转换')
    const response = await callApi('start_conversion', { ...config, preview })
    if (!response.ok) {
      setStatus(response.error || '启动失败')
      appendLog(response.error || '启动失败')
      return
    }
    setRunning(true)
  }

  const stop = async () => {
    await callApi('stop_conversion')
    setStatus('停止请求已发送')
  }

  const openOutput = async () => {
    const response = await callApi('open_output_dir', lastOutputDir || config.outputDir)
    if (!response.ok) {
      appendLog(response.error || '无法打开输出目录')
      setStatus(response.error || '无法打开输出目录')
    }
  }

  return (
    <div className="flex h-full w-full bg-[#f4f1ea] text-slate-950">
      <aside className="thin-scrollbar flex h-full w-[300px] shrink-0 flex-col overflow-y-auto bg-[#181714] px-7 py-6 text-stone-50">
        <div>
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-emerald-500 text-white shadow-lift">
            <BookOpen size={24} />
          </div>
          <h1 className="mt-5 text-3xl font-semibold tracking-normal">TXT EPUB</h1>
          <p className="mt-2 text-sm text-stone-400">小说转换工作台</p>
        </div>

        <div className="mt-6 grid grid-cols-2 gap-2.5">
          <Metric label="来源" value={config.inputs.length} />
          <Metric label="总数" value={stats.total} />
          <Metric label="成功" value={stats.ok} />
          <Metric label="失败" value={stats.failed} />
        </div>

        <div className="mt-6 space-y-2.5">
          <ActionButton icon={FilePlus2} label="添加 TXT" onClick={addTxtFiles} disabled={!ready || running} />
          <ActionButton icon={FolderPlus} label="添加文件夹" onClick={addFolder} disabled={!ready || running} tone="secondary" />
          <ActionButton icon={Eye} label="预览目录" onClick={() => start(true)} disabled={!ready || running} tone="violet" />
          <ActionButton icon={Play} label="开始转换" onClick={() => start(false)} disabled={!ready || running} tone="primary" strong />
          <ActionButton icon={Square} label="停止任务" onClick={stop} disabled={!running} tone="danger" />
        </div>

        <div className="mt-6 space-y-2.5 pb-1">
          <ActionButton icon={FolderOpen} label="打开输出目录" onClick={openOutput} disabled={!ready} tone="ghost" />
          <ActionButton icon={RotateCcw} label="清空输入" onClick={() => updateConfig('inputs', [])} disabled={running} tone="ghost" />
          <div className="rounded-2xl border border-white/10 px-4 py-2.5 text-xs text-stone-400">
            {ready ? '后端已连接' : '等待桌面后端'}
          </div>
        </div>
      </aside>

      <main className="min-w-0 flex-1 overflow-hidden">
        <header className="flex items-start justify-between gap-8 px-9 pb-6 pt-8">
          <div>
            <div className="flex items-center gap-3 text-sm font-medium text-emerald-700">
              <Gauge size={18} />
              <span>{status}</span>
            </div>
            <h2 className="mt-3 text-4xl font-semibold tracking-normal text-[#1d1b17]">TXT 转 EPUB</h2>
          </div>
          <div className="w-[360px] pt-3">
            <div className="mb-2 flex justify-between text-xs text-stone-500">
              <span>{currentFile || '进度'}</span>
              <span>{progress}%</span>
            </div>
            <div className="h-3 overflow-hidden rounded-full bg-stone-300/70">
              <div className="h-full rounded-full bg-emerald-600 transition-all duration-300" style={{ width: `${progress}%` }} />
            </div>
          </div>
        </header>

        <div className="thin-scrollbar h-[calc(100%-128px)] overflow-y-auto px-9 pb-9">
          <div className="grid grid-cols-[minmax(0,1.35fr)_minmax(360px,0.85fr)] gap-6">
            <section className="space-y-6">
              <Surface title="输入">
                <div className="mb-4 flex flex-wrap gap-3">
                  <ToolbarButton icon={FilePlus2} label="TXT" onClick={addTxtFiles} disabled={!ready || running} />
                  <ToolbarButton icon={FolderPlus} label="文件夹" onClick={addFolder} disabled={!ready || running} />
                  <ToolbarButton icon={Trash2} label="清空" onClick={() => updateConfig('inputs', [])} disabled={running || !config.inputs.length} />
                </div>
                <div className="thin-scrollbar min-h-[220px] max-h-[320px] overflow-y-auto rounded-3xl bg-stone-100/80 p-3">
                  {config.inputs.length === 0 ? (
                    <div className="flex h-[190px] items-center justify-center rounded-2xl border border-dashed border-stone-300 text-stone-500">
                      没有输入文件
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {config.inputs.map((item, index) => (
                        <div key={item} className="flex items-center gap-3 rounded-2xl bg-white px-4 py-3 shadow-sm">
                          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-emerald-50 text-emerald-700">
                            {item.toLowerCase().endsWith('.txt') ? <TextCursorInput size={18} /> : <FolderOpen size={18} />}
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="truncate text-sm font-medium text-stone-900">{shortPath(item)}</div>
                            <div className="truncate text-xs text-stone-500">{item}</div>
                          </div>
                          <button
                            type="button"
                            className="rounded-xl p-2 text-stone-400 transition hover:bg-stone-100 hover:text-red-600"
                            onClick={() => removeInput(index)}
                            disabled={running}
                          >
                            <Trash2 size={17} />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </Surface>

              <Surface title="书籍信息">
                <div className="grid grid-cols-2 gap-4">
                  <Field label="书名" value={config.title} onChange={(value) => updateConfig('title', value)} placeholder="自动识别" />
                  <Field label="作者" value={config.author} onChange={(value) => updateConfig('author', value)} placeholder="自动识别" />
                  <PathField
                    icon={Image}
                    label="封面"
                    value={config.coverImage}
                    onChoose={() => choosePath('choose_cover_image', 'coverImage')}
                    onClear={() => updateConfig('coverImage', '')}
                  />
                  <PathField
                    icon={Type}
                    label="字体"
                    value={config.font}
                    onChoose={() => choosePath('choose_font', 'font')}
                    onClear={() => updateConfig('font', '')}
                  />
                </div>
              </Surface>

              <Surface title="运行日志">
                <div className="thin-scrollbar h-[210px] overflow-y-auto rounded-3xl bg-[#181714] p-4 font-mono text-xs leading-6 text-stone-200">
                  {logs.length === 0 ? (
                    <div className="text-stone-500">等待任务</div>
                  ) : (
                    logs.map((line, index) => (
                      <div key={`${line}-${index}`} className="whitespace-pre-wrap break-words">
                        {line}
                      </div>
                    ))
                  )}
                  <div ref={logEndRef} />
                </div>
              </Surface>
            </section>

            <section className="space-y-6">
              <Surface title="输出">
                <PathField
                  icon={FolderOpen}
                  label="输出目录"
                  value={config.outputDir}
                  onChoose={() => choosePath('choose_output_dir', 'outputDir')}
                  onClear={() => updateConfig('outputDir', '')}
                  placeholder="自动创建"
                />
                <SelectField label="编码" value={config.encoding} options={encodingOptions} onChange={(value) => updateConfig('encoding', value)} />
                <div className="mt-4 grid grid-cols-2 gap-3">
                  <Toggle label="递归" checked={config.recursive} onChange={(value) => updateConfig('recursive', value)} />
                  <Toggle label="覆盖" checked={config.overwrite} onChange={(value) => updateConfig('overwrite', value)} />
                  <Toggle label="保留目录" checked={config.keepTocText} onChange={(value) => updateConfig('keepTocText', value)} />
                  <Toggle label="弱标题" checked={config.allowWeakTitle} onChange={(value) => updateConfig('allowWeakTitle', value)} />
                </div>
              </Surface>

              <Surface title="章节规则">
                <div className="grid grid-cols-3 gap-3">
                  <Field label="标题长度" value={config.maxTitleLength} onChange={(value) => updateConfig('maxTitleLength', value)} />
                  <Field label="预览章节" value={config.previewLimit} onChange={(value) => updateConfig('previewLimit', value)} />
                  <Field label="XHTML 字符" value={config.maxCharsPerXhtml} onChange={(value) => updateConfig('maxCharsPerXhtml', value)} />
                </div>
                <TextArea label="额外章节正则" value={config.chapterRegex} onChange={(value) => updateConfig('chapterRegex', value)} rows={5} />
              </Surface>

              <Surface title="元数据">
                <Field label="语言" value={config.language} onChange={(value) => updateConfig('language', value)} />
                <Field label="出版者" value={config.publisher} onChange={(value) => updateConfig('publisher', value)} placeholder="可选" />
                <TextArea label="简介" value={config.description} onChange={(value) => updateConfig('description', value)} rows={6} />
              </Surface>

              <Surface title="结果">
                <div className="space-y-3">
                  {results.length === 0 ? (
                    <div className="rounded-2xl bg-stone-100 px-4 py-5 text-sm text-stone-500">暂无结果</div>
                  ) : (
                    results.slice(-4).map((result, index) => (
                      <div key={`${result.source}-${index}`} className="flex items-start gap-3 rounded-2xl bg-stone-100 px-4 py-3">
                        {result.status === 'failed' ? (
                          <CircleAlert className="mt-0.5 text-red-600" size={18} />
                        ) : (
                          <CheckCircle2 className="mt-0.5 text-emerald-700" size={18} />
                        )}
                        <div className="min-w-0">
                          <div className="truncate text-sm font-medium text-stone-900">{result.title}</div>
                          <div className="text-xs text-stone-500">
                            {result.status} · {result.chapterCount} 章 · {result.encoding}
                          </div>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </Surface>
            </section>
          </div>
        </div>
      </main>

      {running && (
        <div className="pointer-events-none fixed bottom-6 right-7 flex items-center gap-3 rounded-2xl bg-[#181714] px-4 py-3 text-sm text-white shadow-soft">
          <Loader2 className="animate-spin text-emerald-400" size={18} />
          <span>{status}</span>
        </div>
      )}
    </div>
  )
}

function Metric({ label, value }) {
  return (
    <div className="rounded-2xl bg-white/8 px-4 py-2.5 ring-1 ring-white/10">
      <div className="text-2xl font-semibold text-white">{value}</div>
      <div className="mt-1 text-xs text-stone-400">{label}</div>
    </div>
  )
}

function ActionButton({ icon: Icon, label, onClick, disabled, tone = 'default', strong = false }) {
  const tones = {
    default: 'bg-blue-600 hover:bg-blue-700',
    secondary: 'bg-emerald-700 hover:bg-emerald-800',
    violet: 'bg-violet-600 hover:bg-violet-700',
    primary: 'bg-emerald-600 hover:bg-emerald-700',
    danger: 'bg-red-700 hover:bg-red-800',
    ghost: 'bg-white/5 hover:bg-white/10 ring-1 ring-white/10',
  }
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`flex w-full items-center justify-center gap-2 rounded-2xl px-4 text-sm font-medium text-white transition disabled:cursor-not-allowed disabled:opacity-45 ${strong ? 'h-12 text-base' : 'h-11'} ${tones[tone]}`}
    >
      <Icon size={18} />
      {label}
    </button>
  )
}

function Surface({ title, children }) {
  return (
    <section className="rounded-[28px] border border-stone-200/80 bg-white p-5 shadow-soft">
      <div className="mb-5 flex items-center gap-3">
        <div className="h-2 w-2 rounded-full bg-emerald-600" />
        <h3 className="text-lg font-semibold text-stone-950">{title}</h3>
      </div>
      {children}
    </section>
  )
}

function ToolbarButton({ icon: Icon, label, onClick, disabled }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="inline-flex h-10 items-center gap-2 rounded-2xl bg-stone-900 px-4 text-sm font-medium text-white transition hover:bg-stone-700 disabled:cursor-not-allowed disabled:opacity-40"
    >
      <Icon size={17} />
      {label}
    </button>
  )
}

function Field({ label, value, onChange, placeholder = '' }) {
  return (
    <label className="block">
      <span className="mb-2 block text-xs font-medium text-stone-500">{label}</span>
      <input
        value={value ?? ''}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="focus-ring h-11 w-full rounded-2xl border border-stone-300 bg-white px-4 text-sm text-stone-950 placeholder:text-stone-400"
      />
    </label>
  )
}

function SelectField({ label, value, options, onChange }) {
  return (
    <label className="mt-4 block">
      <span className="mb-2 block text-xs font-medium text-stone-500">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="focus-ring h-11 w-full rounded-2xl border border-stone-300 bg-white px-4 text-sm text-stone-950"
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </label>
  )
}

function PathField({ icon: Icon = LibraryBig, label, value, onChoose, onClear, placeholder = '未选择' }) {
  return (
    <div>
      <span className="mb-2 block text-xs font-medium text-stone-500">{label}</span>
      <div className="flex items-center gap-2 rounded-2xl border border-stone-300 bg-white p-1.5">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-stone-100 text-stone-700">
          <Icon size={17} />
        </div>
        <div className="min-w-0 flex-1 truncate text-sm text-stone-700">{value ? shortPath(value) : placeholder}</div>
        {value && (
          <button type="button" onClick={onClear} className="rounded-xl p-2 text-stone-400 transition hover:bg-stone-100 hover:text-red-600">
            <Trash2 size={16} />
          </button>
        )}
        <button type="button" onClick={onChoose} className="rounded-xl bg-stone-900 px-3 py-2 text-xs font-medium text-white transition hover:bg-stone-700">
          选择
        </button>
      </div>
    </div>
  )
}

function Toggle({ label, checked, onChange }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className={`flex h-12 items-center justify-between rounded-2xl px-4 text-sm font-medium transition ${
        checked ? 'bg-emerald-50 text-emerald-800 ring-1 ring-emerald-200' : 'bg-stone-100 text-stone-600 ring-1 ring-stone-200'
      }`}
    >
      <span>{label}</span>
      <span className={`h-5 w-9 rounded-full p-0.5 transition ${checked ? 'bg-emerald-600' : 'bg-stone-300'}`}>
        <span className={`block h-4 w-4 rounded-full bg-white transition ${checked ? 'translate-x-4' : ''}`} />
      </span>
    </button>
  )
}

function TextArea({ label, value, onChange, rows = 5 }) {
  return (
    <label className="mt-4 block">
      <span className="mb-2 block text-xs font-medium text-stone-500">{label}</span>
      <textarea
        value={value}
        rows={rows}
        onChange={(event) => onChange(event.target.value)}
        className="focus-ring thin-scrollbar w-full resize-y rounded-2xl border border-stone-300 bg-white px-4 py-3 text-sm text-stone-950 placeholder:text-stone-400"
      />
    </label>
  )
}
