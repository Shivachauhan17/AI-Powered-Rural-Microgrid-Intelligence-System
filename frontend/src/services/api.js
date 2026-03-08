const BASE = import.meta.env.VITE_API_URL || ''

async function req(path, opts = {}) {
  const res = await fetch(`${BASE}/api/v1${path}`, {
    headers: { 'Content-Type': 'application/json', ...opts.headers },
    ...opts,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

export const getDashboardStats     = () => req('/dashboard/stats')
export const get24hProfile         = () => req('/dashboard/24h-profile')
export const getHouseAllocations   = () => req('/dashboard/house-allocations')
export const getAllDemandForecasts  = (hours = 24) => req(`/forecast/demand?hours=${hours}`)
export const getSolarForecast      = (cap = 30.0)  => req(`/forecast/solar?capacity_kw=${cap}`)
export const getModelMetrics       = () => req('/forecast/metrics')
export const simulateOptimization  = () => req('/optimize/simulate')
export const runOptimization       = (body) => req('/optimize/allocate', { method:'POST', body:JSON.stringify(body) })
export const getAlerts             = () => req('/alerts/')

export function createRealtimeSocket(onMsg, onErr) {
  const proto = window.location.protocol === 'https:' ? 'wss://' : 'ws://'
  const ws    = new WebSocket(`${proto}${window.location.host}/api/v1/dashboard/ws/realtime`)
  ws.onmessage = e => { try { onMsg(JSON.parse(e.data)) } catch (_) {} }
  ws.onerror   = () => onErr?.()
  ws.onclose   = () => onErr?.()
  return ws
}
