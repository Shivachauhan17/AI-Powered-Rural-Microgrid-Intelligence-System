import { useState, useEffect, useCallback, useRef } from 'react'

/**
 * Generic data-fetching hook.
 * @param {Function} fetcher  - async function returning data
 * @param {any}      fallback - value while loading or on error
 * @param {number}   pollMs  - if > 0, auto-refetch every N ms
 */
export function useFetch(fetcher, fallback = null, pollMs = 0) {
  const [data, setData] = useState(fallback)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const timerRef = useRef(null)

  const load = useCallback(async () => {
    try {
      setError(null)
      const result = await fetcher()
      setData(result)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [fetcher])

  useEffect(() => {
    load()
    if (pollMs > 0) {
      timerRef.current = setInterval(load, pollMs)
    }
    return () => clearInterval(timerRef.current)
  }, [load, pollMs])

  return { data, loading, error, refetch: load }
}


/**
 * WebSocket hook for real-time readings.
 * Falls back to polling /dashboard/stats every 5s if WS fails.
 */
import { createRealtimeSocket } from '../services/api'
import { getDashboardStats } from '../services/api'

export function useRealtime() {
  const [reading, setReading] = useState(null)
  const [wsConnected, setWsConnected] = useState(false)
  const wsRef = useRef(null)
  const pollRef = useRef(null)

  const startPolling = useCallback(() => {
    setWsConnected(false)
    clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const stats = await getDashboardStats()
        setReading({
          timestamp: new Date().toLocaleTimeString(),
          solar_kw: stats.current_solar_kw,
          demand_kw: stats.current_demand_kw,
          battery_soc: stats.battery_soc_pct,
          net_kw: stats.net_energy_kw,
        })
      } catch (_) {}
    }, 5000)
  }, [])

  useEffect(() => {
    const ws = createRealtimeSocket(
      (msg) => {
        setReading(msg)
        setWsConnected(true)
      },
      () => startPolling()
    )
    wsRef.current = ws

    // Also fetch immediately
    getDashboardStats().then(stats => {
      setReading({
        timestamp: new Date().toLocaleTimeString(),
        solar_kw: stats.current_solar_kw,
        demand_kw: stats.current_demand_kw,
        battery_soc: stats.battery_soc_pct,
        net_kw: stats.net_energy_kw,
      })
    }).catch(() => {})

    return () => {
      ws.close()
      clearInterval(pollRef.current)
    }
  }, [startPolling])

  return { reading, wsConnected }
}
