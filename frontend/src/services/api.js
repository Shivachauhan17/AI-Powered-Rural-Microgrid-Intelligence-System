// ─── API Service Layer ─────────────────────────────────────────────────────
// All calls go to FastAPI backend. BASE_URL is set via env variable.
// In dev: Vite proxy forwards /api → http://localhost:8000
// In prod: nginx proxy forwards /api → backend container

const BASE_URL = import.meta.env.VITE_API_URL || ''

async function request(path, options = {}) {
  const url = `${BASE_URL}/api/v1${path}`
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

// ─── Dashboard ────────────────────────────────────────────────────────────
export const getDashboardStats = () => request('/dashboard/stats')
export const get24hProfile = () => request('/dashboard/24h-profile')
export const getHouseAllocations = () => request('/dashboard/house-allocations')

// ─── Forecast ─────────────────────────────────────────────────────────────
export const getAllDemandForecasts = (hours = 24) =>
  request(`/forecast/demand?hours=${hours}`)

export const getHouseDemandForecast = (houseId, hours = 24) =>
  request(`/forecast/demand/${houseId}?hours=${hours}`)

export const getSolarForecast = (capacityKw = 30.0) =>
  request(`/forecast/solar?capacity_kw=${capacityKw}`)

export const getModelMetrics = () => request('/forecast/metrics')

// ─── Optimization ─────────────────────────────────────────────────────────
export const simulateOptimization = () => request('/optimize/simulate')

export const runOptimization = (payload) =>
  request('/optimize/allocate', {
    method: 'POST',
    body: JSON.stringify(payload),
  })

// ─── Alerts ───────────────────────────────────────────────────────────────
export const getAlerts = () => request('/alerts/')

// ─── Health ───────────────────────────────────────────────────────────────
export const getHealth = () => request('/health').catch(() => null)

// ─── WebSocket ────────────────────────────────────────────────────────────
export function createRealtimeSocket(onMessage, onError) {
  const wsBase = import.meta.env.VITE_WS_URL ||
    (window.location.protocol === 'https:' ? 'wss://' : 'ws://') + window.location.host
  const url = `${wsBase}/api/v1/dashboard/ws/realtime`

  const ws = new WebSocket(url)

  ws.onmessage = (e) => {
    try { onMessage(JSON.parse(e.data)) } catch (_) {}
  }
  ws.onerror = () => onError?.()
  ws.onclose = () => onError?.()

  return ws
}
