import { useState, useEffect, useCallback, useRef } from 'react'
import {
  Sun, Battery, Zap, Home, Activity, TrendingUp,
  Wifi, WifiOff, Bell, MapPin, RefreshCw, Loader,
} from 'lucide-react'
import {
  AreaChart, Area, BarChart, Bar, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, PieChart, Pie, Cell,
} from 'recharts'
import {
  getDashboardStats, get24hProfile, getHouseAllocations,
  getAllDemandForecasts, getSolarForecast, getModelMetrics,
  simulateOptimization, getAlerts,
} from './services/api'

// ── Generic polling hook ───────────────────────────────────────────────────
function useFetch(fn, fallback, pollMs = 0) {
  const [data,    setData]    = useState(fallback ?? null)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)
  const timer = useRef(null)
  const fnRef = useRef(fn)
  fnRef.current = fn

  const load = useCallback(async () => {
    try {
      setError(null)
      setData(await fnRef.current())
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    if (pollMs > 0) timer.current = setInterval(load, pollMs)
    return () => clearInterval(timer.current)
  }, [load, pollMs])

  return { data, loading, error, refetch: load }
}

// ── WebSocket / polling realtime hook ──────────────────────────────────────
function useRealtime() {
  const [reading, setReading] = useState(null)
  const [connected, setConnected] = useState(false)
  const pollRef = useRef(null)

  useEffect(() => {
    const poll = async () => {
      try {
        const s = await getDashboardStats()
        setReading({
          timestamp:   new Date().toLocaleTimeString(),
          solar_kw:    s.current_solar_kw,
          demand_kw:   s.current_demand_kw,
          battery_soc: s.battery_soc_pct,
          net_kw:      s.net_energy_kw,
        })
      } catch (_) {}
    }

    let ws = null
    try {
      const proto = window.location.protocol === 'https:' ? 'wss://' : 'ws://'
      ws = new WebSocket(`${proto}${window.location.host}/api/v1/dashboard/ws/realtime`)
      ws.onopen    = () => setConnected(true)
      ws.onmessage = e => { try { setReading(JSON.parse(e.data)) } catch (_) {} }
      ws.onerror   = () => { setConnected(false); pollRef.current = setInterval(poll, 5000) }
      ws.onclose   = () => setConnected(false)
    } catch (_) {
      pollRef.current = setInterval(poll, 5000)
    }
    poll()
    return () => { ws?.close(); clearInterval(pollRef.current) }
  }, [])

  return { reading, connected }
}

// ── UI atoms ──────────────────────────────────────────────────────────────
const Spinner = () => (
  <div style={{ display:'flex', alignItems:'center', justifyContent:'center', height:120, color:'#64748b' }}>
    <Loader size={22} style={{ animation:'spin 1s linear infinite' }} />
    <span style={{ marginLeft:10, fontSize:13 }}>Loading data…</span>
  </div>
)

const ErrBox = ({ msg, onRetry }) => (
  <div style={{ background:'#ef444415', border:'1px solid #ef444430', borderRadius:10, padding:'12px 16px', display:'flex', gap:12, alignItems:'center', justifyContent:'space-between' }}>
    <span style={{ color:'#ef4444', fontSize:13 }}>⚠ Could not load data: {msg}</span>
    {onRetry && <button onClick={onRetry} style={{ background:'#ef444420', border:'1px solid #ef444440', color:'#ef4444', borderRadius:6, padding:'5px 12px', cursor:'pointer', fontSize:12 }}>Retry</button>}
  </div>
)

function StatCard({ icon: Icon, label, value, unit, sub, color, loading: isLoading }) {
  return (
    <div className="stat-card">
      <div className="stat-icon" style={{ background:`${color}22`, color }}><Icon size={20}/></div>
      {isLoading
        ? <div style={{ height:32, background:'#1e293b', borderRadius:6, marginTop:8, animation:'pulse 1.5s ease-in-out infinite' }}/>
        : <div className="stat-value">{value}<span className="stat-unit"> {unit}</span></div>}
      <div className="stat-label">{label}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  )
}

function BatteryGauge({ soc }) {
  const color = soc > 60 ? '#22c55e' : soc > 30 ? '#eab308' : '#ef4444'
  const d     = [{ value: soc, fill: color }, { value: 100 - soc, fill: '#1e293b' }]
  return (
    <div style={{ position:'relative', display:'flex', alignItems:'center', justifyContent:'center', margin:'8px 0' }}>
      <PieChart width={120} height={120}>
        <Pie data={d} cx={55} cy={55} innerRadius={38} outerRadius={52} startAngle={90} endAngle={-270} dataKey="value" stroke="none">
          {d.map((x, i) => <Cell key={i} fill={x.fill}/>)}
        </Pie>
      </PieChart>
      <div style={{ position:'absolute', textAlign:'center' }}>
        <div style={{ fontSize:20, fontWeight:700, fontFamily:'IBM Plex Mono,monospace', color }}>{soc}%</div>
        <div style={{ fontSize:10, color:'#64748b' }}>Charged</div>
      </div>
    </div>
  )
}

function HouseCard({ house }) {
  const sat   = +(house.satisfaction_pct ?? 0)
  const dem   = +(house.demand_kw ?? 0)
  const alloc = +(house.allocated_kw ?? 0)
  const color = sat > 90 ? '#22c55e' : sat > 50 ? '#eab308' : '#ef4444'
  const icon  = { clinic:'🏥', school:'🏫', pump:'💧' }[house.id] || '🏠'
  const prioLabel = { critical:'🔴 Must Serve', high:'🟡 Important', normal:'🟢 Normal' }[house.priority] || house.priority
  return (
    <div className={`house-card priority-${house.priority}`}>
      <div className="house-top">
        <span style={{ fontSize:20 }}>{icon}</span>
        <div style={{ flex:1 }}>
          <span style={{ fontSize:12, fontWeight:600, display:'block', textTransform:'capitalize' }}>
            {house.id.replace('_',' ')}
          </span>
          <span style={{ fontSize:10, color }}>{prioLabel}</span>
        </div>
        <div style={{ width:8, height:8, borderRadius:'50%', background:color }}/>
      </div>
      <div style={{ background:'#1e293b', borderRadius:999, height:4, overflow:'hidden' }}>
        <div style={{ width:`${sat}%`, height:'100%', background:color, borderRadius:999, transition:'width .6s ease' }}/>
      </div>
      <div style={{ display:'flex', justifyContent:'space-between', fontSize:11, color:'#64748b' }}>
        <span>{alloc.toFixed(2)} / {dem.toFixed(2)} kW</span>
        <span style={{ color }}>{sat.toFixed(1)}%</span>
      </div>
    </div>
  )
}

function AlertBadge({ level }) {
  const colors = { info:'#0ea5e9', warning:'#f97316', critical:'#ef4444' }
  const labels = { info:'💡 Info', warning:'⚠ Warning', critical:'🚨 Urgent' }
  return <span className="alert-badge" style={{ background:colors[level] }}>{labels[level]}</span>
}

// ── Main App ──────────────────────────────────────────────────────────────
const TAB_TITLES = {
  dashboard: 'Live Energy Overview',
  forecast:  'Energy Predictions',
  optimize:  'Smart Power Distribution',
  houses:    'Home-by-Home Status',
  alerts:    'Warnings & Notifications',
}

export default function App() {
  const [tab, setTab] = useState('dashboard')
  const { reading, connected } = useRealtime()

  const stats    = useFetch(getDashboardStats,     null, 30000)
  const profile  = useFetch(get24hProfile,         null, 60000)
  const houseData= useFetch(getHouseAllocations,   null, 15000)
  const forecasts= useFetch(getAllDemandForecasts,  [],  120000)
  const solar    = useFetch(getSolarForecast,       null, 120000)
  const optim    = useFetch(simulateOptimization,   null, 30000)
  const alertsQ  = useFetch(getAlerts,              [],   20000)
  const metricsQ = useFetch(getModelMetrics,        [],  300000)

  const chartData = profile.data
    ? profile.data.hours.map((h, i) => ({
        hour:    h,
        solar:   profile.data.solar_kw[i],
        demand:  profile.data.demand_kw[i],
        battery: profile.data.battery_soc_pct[i],
        net:     profile.data.net_kw[i],
      }))
    : []

  const s = stats.data

  return (
    <div className="app">
      <style>{CSS}</style>

      {/* ── Sidebar ── */}
      <aside className="sidebar">
        <div className="logo">
          <span style={{ fontSize:24 }}>⚡</span>
          <div>
            <div style={{ fontSize:14, fontWeight:700, color:'#f59e0b' }}>MicroGrid AI</div>
            <div style={{ fontSize:10, color:'#64748b' }}>Smart Village Energy</div>
          </div>
        </div>
        <nav className="nav">
          {[
            { id:'dashboard', label:'Live Overview',    Icon:Activity   },
            { id:'forecast',  label:'Energy Forecast',  Icon:TrendingUp },
            { id:'optimize',  label:'Power Sharing',    Icon:Zap        },
            { id:'houses',    label:'All Homes',         Icon:Home       },
            { id:'alerts',    label:'Warnings',          Icon:Bell       },
          ].map(({ id, label, Icon }) => (
            <button key={id} className={`nav-btn ${tab === id ? 'active' : ''}`} onClick={() => setTab(id)}>
              <Icon size={17}/> <span>{label}</span>
              {id === 'alerts' && (alertsQ.data?.filter(a => a.level !== 'info').length > 0) && (
                <span className="badge">{alertsQ.data.filter(a => a.level !== 'info').length}</span>
              )}
            </button>
          ))}
        </nav>
        <div style={{ borderTop:'1px solid #1e293b', paddingTop:12, fontSize:11, color:'#64748b', display:'flex', flexDirection:'column', gap:5 }}>
          <div style={{ display:'flex', alignItems:'center', gap:6 }}>
            {connected ? <Wifi size={13} color="#22c55e"/> : <WifiOff size={13} color="#f97316"/>}
            <span style={{ color: connected ? '#22c55e' : '#f97316' }}>{connected ? 'Live Updates' : 'Auto-refresh'}</span>
          </div>
          {reading && <div>⚡ {reading.timestamp}</div>}
          <div><MapPin size={11} style={{ display:'inline', marginRight:4 }}/>Rampur Village, UP</div>
        </div>
      </aside>

      {/* ── Main ── */}
      <main className="main">
        <header className="topbar">
          <div>
            <h1 style={{ fontSize:20, fontWeight:700 }}>{TAB_TITLES[tab]}</h1>
            <p style={{ fontSize:12, color:'#64748b', marginTop:2 }}>
              10 homes · 30 kW solar panels · 50 kWh battery storage · AI-powered
            </p>
          </div>
          <div style={{ display:'flex', alignItems:'center', gap:12 }}>
            {s && (
              <div className={`risk-badge ${s.blackout_risk}`}>
                {s.blackout_risk === 'high' ? '🔴 High Risk' : s.blackout_risk === 'medium' ? '🟡 Medium Risk' : '🟢 Low Risk'}
              </div>
            )}
            <button className="refresh-btn" onClick={() => { stats.refetch(); profile.refetch(); houseData.refetch() }}>
              <RefreshCw size={13}/> Refresh
            </button>
          </div>
        </header>

        <div className="content">

          {/* ── DASHBOARD ── */}
          {tab === 'dashboard' && (<>
            {stats.error && <ErrBox msg={stats.error} onRetry={stats.refetch}/>}

            {reading && (
              <div className="live-bar">
                <span className="live-dot"/><span style={{ color:'#22c55e', fontWeight:700, fontSize:10, letterSpacing:'.1em' }}>LIVE</span>
                <span style={{ color:'#64748b' }}>☀️ Solar Power: <strong style={{ color:'#e2e8f0' }}>{reading.solar_kw} kW</strong></span>
                <span style={{ color:'#64748b' }}>⚡ Village Demand: <strong style={{ color:'#e2e8f0' }}>{reading.demand_kw} kW</strong></span>
                <span style={{ color:'#64748b' }}>🔋 Battery Charge: <strong style={{ color:'#e2e8f0' }}>{reading.battery_soc}%</strong></span>
                <span style={{ color:'#64748b' }}>Balance: <strong style={{ color: reading.net_kw >= 0 ? '#22c55e' : '#ef4444' }}>{reading.net_kw >= 0 ? '+' : ''}{reading.net_kw} kW</strong></span>
              </div>
            )}

            <div className="stats-grid">
              <StatCard icon={Sun}        loading={stats.loading} color="#f59e0b" label="Solar Power Now"    value={s?.current_solar_kw ?? '—'}              unit="kW" sub={`Total today: ${s?.today_solar_kwh ?? '—'} kWh`}/>
              <StatCard icon={Zap}        loading={stats.loading} color="#6366f1" label="Village Power Need" value={s?.current_demand_kw?.toFixed(1) ?? '—'}  unit="kW" sub={`Total today: ${s?.today_demand_kwh ?? '—'} kWh`}/>
              <StatCard icon={Battery}    loading={stats.loading} color="#22c55e" label="Battery Charge"     value={s?.battery_soc_pct ?? '—'}               unit="%"  sub="Full charge = 50 units stored"/>
              <StatCard icon={TrendingUp} loading={stats.loading} color="#0ea5e9" label="Energy Saved by AI" value={s?.savings_pct ?? '—'}                   unit="%"  sub="compared to no AI system"/>
            </div>

            <div style={{ display:'flex', gap:16 }}>
              <div className="chart-card" style={{ flex:'2.5' }}>
                <h3 className="chart-title">Today's Solar Generation vs Village Power Demand</h3>
                <p className="chart-desc">Green area = solar energy produced · Purple area = power needed by village · Dashed line = battery charge level</p>
                {profile.loading ? <Spinner/> : profile.error ? <ErrBox msg={profile.error} onRetry={profile.refetch}/> : (
                  <ResponsiveContainer width="100%" height={250}>
                    <AreaChart data={chartData}>
                      <defs>
                        <linearGradient id="gS" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#f59e0b" stopOpacity={0.35}/><stop offset="100%" stopColor="#f59e0b" stopOpacity={0}/></linearGradient>
                        <linearGradient id="gD" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#6366f1" stopOpacity={0.35}/><stop offset="100%" stopColor="#6366f1" stopOpacity={0}/></linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e293b"/>
                      <XAxis dataKey="hour" tick={{ fill:'#64748b', fontSize:11 }} tickLine={false} interval={3}/>
                      <YAxis tick={{ fill:'#64748b', fontSize:11 }} tickLine={false} unit=" kW"/>
                      <Tooltip contentStyle={{ background:'#0f172a', border:'1px solid #1e293b', borderRadius:8 }} labelStyle={{ color:'#94a3b8', fontSize:12 }} itemStyle={{ color:'#f1f5f9', fontSize:13 }}/>
                      <Legend/>
                      <Area type="monotone" dataKey="solar"  stroke="#f59e0b" fill="url(#gS)" strokeWidth={2}   name="Solar (kW)"  dot={false}/>
                      <Area type="monotone" dataKey="demand" stroke="#6366f1" fill="url(#gD)" strokeWidth={2}   name="Demand (kW)" dot={false}/>
                      <Line type="monotone" dataKey="battery" stroke="#22c55e" strokeWidth={1.5} strokeDasharray="4 2" name="Battery (%)" dot={false}/>
                    </AreaChart>
                  </ResponsiveContainer>
                )}
              </div>

              <div className="chart-card" style={{ flex:1, display:'flex', flexDirection:'column', alignItems:'center' }}>
                <h3 className="chart-title">Battery Status</h3>
                {stats.loading ? <Spinner/> : <>
                  <BatteryGauge soc={s?.battery_soc_pct ?? 0}/>
                  <div style={{ width:'100%', display:'flex', flexDirection:'column', gap:8, marginTop:8 }}>
                    {[
                      ['Current Shortage', `${s?.deficit_kw ?? 0} kW`],
                      ['Current Surplus',  `${s?.surplus_kw ?? 0} kW`],
                      ['Homes Connected',  s?.active_houses ?? '—'],
                      ['Blackout Risk',    s?.blackout_risk ?? '—'],
                    ].map(([k, v]) => (
                      <div key={k} style={{ display:'flex', justifyContent:'space-between', fontSize:12, color:'#64748b', borderBottom:'1px solid #1e293b', paddingBottom:6 }}>
                        <span>{k}</span><strong style={{ color:'#e2e8f0' }}>{v}</strong>
                      </div>
                    ))}
                  </div>
                </>}
              </div>
            </div>

            <div className="chart-card">
              <h3 className="chart-title">Hourly Power Balance (Green = surplus going to battery · Red = shortage)</h3>
              {profile.loading ? <Spinner/> : (
                <ResponsiveContainer width="100%" height={180}>
                  <BarChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b"/>
                    <XAxis dataKey="hour" tick={{ fill:'#64748b', fontSize:10 }} tickLine={false} interval={3}/>
                    <YAxis tick={{ fill:'#64748b', fontSize:11 }} unit=" kW"/>
                    <Tooltip
                      contentStyle={{ background:'#1e293b', border:'1px solid #334155', borderRadius:8, padding:'8px 12px' }}
                      labelStyle={{ color:'#94a3b8', fontSize:12, marginBottom:4 }}
                      itemStyle={{ color:'#f1f5f9', fontSize:13, fontWeight:600 }}
                      cursor={{ fill:'rgba(255,255,255,0.05)' }}
                    />
                    <Bar dataKey="net" name="Net kW" radius={[3,3,0,0]}>
                      {chartData.map((d, i) => <Cell key={i} fill={d.net >= 0 ? '#22c55e' : '#ef4444'} fillOpacity={0.8}/>)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>
          </>)}

          {/* ── FORECAST ── */}
          {tab === 'forecast' && (<>
            <div className="chart-card">
              <h3 className="chart-title">Solar Generation Forecast – Next 24 Hours</h3>
              <p className="chart-desc">AI prediction of how much solar power will be generated · Peak: {solar.data?.peak_generation_kw ?? '—'} kW at {solar.data?.peak_hour ?? '—'}:00 · Cloud cover: {solar.data?.cloud_cover_estimate != null ? `${(solar.data.cloud_cover_estimate*100).toFixed(0)}%` : '—'}</p>
              {solar.loading ? <Spinner/> : solar.error ? <ErrBox msg={solar.error} onRetry={solar.refetch}/> : (
                <ResponsiveContainer width="100%" height={250}>
                  <AreaChart data={(solar.data?.hourly_generation_kw ?? []).map((v, i) => ({ hour:`${String(i).padStart(2,'0')}:00`, solar:v }))}>
                    <defs><linearGradient id="gSol" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#f59e0b" stopOpacity={0.4}/><stop offset="100%" stopColor="#f59e0b" stopOpacity={0}/></linearGradient></defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b"/>
                    <XAxis dataKey="hour" tick={{ fill:'#64748b', fontSize:11 }} interval={2} tickLine={false}/>
                    <YAxis tick={{ fill:'#64748b', fontSize:11 }} unit=" kW"/>
                    <Tooltip contentStyle={{ background:'#1e293b', border:'1px solid #334155', borderRadius:8 }}/>
                    <Area type="monotone" dataKey="solar" stroke="#f59e0b" fill="url(#gSol)" strokeWidth={2.5} name="Solar kW" dot={false}/>
                  </AreaChart>
                </ResponsiveContainer>
              )}
            </div>

            <div className="chart-card">
              <h3 className="chart-title">How Much Power Each Home Will Need Tomorrow</h3>
              <p className="chart-desc">AI prediction based on past usage patterns · Red = must serve first · Green = normal homes</p>
              {forecasts.loading ? <Spinner/> : forecasts.error ? <ErrBox msg={forecasts.error} onRetry={forecasts.refetch}/> : (
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={forecasts.data.map(h => ({
                    name:      h.house_id.replace('house_','H').replace('clinic','Clinic').replace('school','School').replace('pump','Pump'),
                    daily_kwh: h.total_daily_kwh,
                    priority:  h.priority,
                  }))}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b"/>
                    <XAxis dataKey="name" tick={{ fill:'#64748b', fontSize:10 }} angle={-30} textAnchor="end" height={60}/>
                    <YAxis tick={{ fill:'#64748b', fontSize:11 }} unit=" kWh"/>
                    <Tooltip contentStyle={{ background:'#1e293b', border:'1px solid #334155', borderRadius:8 }}/>
                    <Legend/>
                    <Bar dataKey="daily_kwh" name="Daily kWh" radius={[4,4,0,0]}>
                      {forecasts.data.map((h, i) => <Cell key={i} fill={h.priority==='critical'?'#ef4444':h.priority==='high'?'#f97316':'#22c55e'} fillOpacity={0.85}/>)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>

            <div className="chart-card">
              <h3 className="chart-title">How Accurate Are Our AI Predictions?</h3>
              <p className="chart-desc">Lower numbers = more accurate predictions. Our AI is tested against real data before being used.</p>
              {metricsQ.loading ? <Spinner/> : metricsQ.error ? <ErrBox msg={metricsQ.error} onRetry={metricsQ.refetch}/> : (
                <div style={{ overflowX:'auto' }}>
                  <table style={{ width:'100%', borderCollapse:'collapse', fontSize:13 }}>
                    <thead>
                      <tr>{['Home / Location','Avg Error (kW)','Worst Error (kW)','Error %','AI Model Used'].map(c => (
                        <th key={c} style={{ textAlign:'left', padding:'10px 16px', background:'#1e293b', color:'#64748b', fontSize:11, textTransform:'uppercase', letterSpacing:'.08em', borderBottom:'1px solid #1e293b' }}>{c}</th>
                      ))}</tr>
                    </thead>
                    <tbody>{metricsQ.data.map(m => (
                      <tr key={m.house_id} style={{ borderBottom:'1px solid #1e293b' }}>
                        <td style={{ padding:'10px 16px', fontFamily:'IBM Plex Mono,monospace' }}>{m.house_id}</td>
                        <td style={{ padding:'10px 16px', fontFamily:'IBM Plex Mono,monospace', color:'#22c55e' }}>{m.mae_kw}</td>
                        <td style={{ padding:'10px 16px', fontFamily:'IBM Plex Mono,monospace', color:'#0ea5e9' }}>{m.rmse_kw}</td>
                        <td style={{ padding:'10px 16px', fontFamily:'IBM Plex Mono,monospace', color:'#f59e0b' }}>{m.mape_pct}%</td>
                        <td style={{ padding:'10px 16px' }}><span style={{ background:'#3b82f620', color:'#3b82f6', padding:'2px 8px', borderRadius:999, fontSize:10, fontWeight:700 }}>{m.model_type}</span></td>
                      </tr>
                    ))}</tbody>
                  </table>
                </div>
              )}
            </div>
          </>)}

          {/* ── OPTIMIZE ── */}
          {tab === 'optimize' && (<>
            {optim.error && <ErrBox msg={optim.error} onRetry={optim.refetch}/>}

            <div className="opt-header">
              <div>
                <h2 style={{ fontSize:16, fontWeight:700, marginBottom:4 }}>AI Power Sharing Engine</h2>
                <p style={{ fontSize:12, color:'#64748b', fontFamily:'IBM Plex Mono,monospace' }}>AI decides who gets how much power — clinic and school always served first</p>
                {optim.data && (
                  <p style={{ fontSize:12, color:'#94a3b8', marginTop:6 }}>
                    Power Available: <strong style={{ color:'#e2e8f0' }}>{optim.data.total_available_kw} kW</strong> ·
                    Power Needed: <strong style={{ color:'#e2e8f0' }}>{optim.data.total_demanded_kw} kW</strong> ·
                    Fairness Score: <strong style={{ color:'#22c55e' }}>{optim.data.fairness_index}</strong> ·
                    Homes Without Enough Power: <strong style={{ color:'#f97316' }}>{optim.data.unmet_demand_pct}%</strong>
                  </p>
                )}
              </div>
              {optim.data && (
                <div style={{ padding:'8px 16px', borderRadius:8, fontSize:12, fontWeight:600, ...(optim.data.blackout_risk==='low' ? { background:'#22c55e18', color:'#22c55e', border:'1px solid #22c55e30' } : { background:'#f9731618', color:'#f97316', border:'1px solid #f9731630' }) }}>
                  {optim.data.blackout_risk === 'low' ? '✅ Enough Power' : '⚠️ Not Enough Power'}
                </div>
              )}
            </div>

            {optim.data?.recommendation && (
              <div style={{ background:'#0ea5e910', border:'1px solid #0ea5e930', borderRadius:10, padding:'12px 16px', fontSize:13, color:'#0ea5e9' }}>
                {optim.data.recommendation}
              </div>
            )}

            {optim.loading ? <Spinner/> : optim.data && (<>
              <div className="alloc-table">
                <div className="alloc-header">
                  <span>Home / Location</span><span>Priority</span><span>Power Needed</span><span>Power Given</span><span>Supply Level</span><span>Status</span>
                </div>
                {optim.data.allocations.map(a => (
                  <div key={a.consumer_id} className="alloc-row">
                    <span style={{ fontWeight:500 }}>{({clinic:'🏥',school:'🏫',pump:'💧'})[a.consumer_id]||'🏠'} {a.consumer_id.replace('_',' ')}</span>
                    <span className={`priority-tag ${a.priority}`}>
                      {{ critical:'🔴 Must Serve', high:'🟡 Important', normal:'🟢 Normal' }[a.priority]}
                    </span>
                    <span style={{ fontFamily:'IBM Plex Mono,monospace' }}>{a.demanded_kw} kW</span>
                    <span style={{ fontFamily:'IBM Plex Mono,monospace' }}>{a.allocated_kw} kW</span>
                    <span>
                      <div style={{ background:'#1e293b', borderRadius:999, height:4, overflow:'hidden', width:80, display:'inline-block', marginRight:6, verticalAlign:'middle' }}>
                        <div style={{ width:`${a.satisfaction_pct}%`, height:'100%', background:a.satisfaction_pct>=90?'#22c55e':a.satisfaction_pct>=60?'#eab308':'#ef4444', borderRadius:999 }}/>
                      </div>
                      <span style={{ fontSize:11, color:'#64748b' }}>{a.satisfaction_pct}%</span>
                    </span>
                    <span className={`status-tag ${a.status}`}>
                      {{ full:'Fully Powered', partial:'Partial Power', 'critical-low':'No Power' }[a.status] || a.status}
                    </span>
                  </div>
                ))}
              </div>

              <div className="chart-card">
                <h3 className="chart-title">Power Given vs Power Needed — Each Location</h3>
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={optim.data.allocations.map(a => ({
                    name:      a.consumer_id.replace('house_','H').replace('clinic','Clinic').replace('school','School').replace('pump','Pump'),
                    demanded:  a.demanded_kw,
                    allocated: a.allocated_kw,
                  }))}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b"/>
                    <XAxis dataKey="name" tick={{ fill:'#64748b', fontSize:10 }} angle={-30} textAnchor="end" height={60}/>
                    <YAxis tick={{ fill:'#64748b', fontSize:11 }} unit=" kW"/>
                    <Tooltip contentStyle={{ background:'#1e293b', border:'1px solid #334155', borderRadius:8 }}/>
                    <Legend/>
                    <Bar dataKey="demanded"  fill="#6366f1" name="Demanded"  radius={[3,3,0,0]} fillOpacity={0.5}/>
                    <Bar dataKey="allocated" fill="#22c55e" name="Allocated" radius={[3,3,0,0]} fillOpacity={0.9}/>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </>)}
          </>)}

          {/* ── HOUSES ── */}
          {tab === 'houses' && (<>
            {houseData.error && <ErrBox msg={houseData.error} onRetry={houseData.refetch}/>}
            {houseData.loading ? <Spinner/> : houseData.data && (<>
              <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:12 }}>
                {[
                  ['🏠 Total Locations', `${houseData.data.houses?.length ?? 13}`],
                  ['☀️ Solar Right Now', `${houseData.data.current_solar_kw} kW`],
                  ['📊 Total Power Needed', `${houseData.data.total_demand_kw?.toFixed(1)} kW`],
                  ['🕒 Last Refreshed', new Date(houseData.data.timestamp).toLocaleTimeString()],
                ].map(([k, v]) => (
                  <div key={k} style={{ background:'#0f172a', border:'1px solid #1e293b', borderRadius:10, padding:'14px 18px' }}>
                    <div style={{ fontSize:12, color:'#64748b' }}>{k}</div>
                    <div style={{ fontSize:18, fontWeight:700, fontFamily:'IBM Plex Mono,monospace', marginTop:4 }}>{v}</div>
                  </div>
                ))}
              </div>
              <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(210px,1fr))', gap:12 }}>
                {houseData.data.houses?.map(h => <HouseCard key={h.id} house={h}/>)}
              </div>
            </>)}
          </>)}

          {/* ── ALERTS ── */}
          {tab === 'alerts' && (
            <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
              {alertsQ.error && <ErrBox msg={alertsQ.error} onRetry={alertsQ.refetch}/>}
              {alertsQ.loading ? <Spinner/> : (<>
                <div style={{ display:'flex', gap:12 }}>
                  {['critical','warning','info'].map(lvl => (
                    <span key={lvl} className={`al-count ${lvl}`}>
                      {lvl==='critical'?'🚨':lvl==='warning'?'⚠️':'💡'} {alertsQ.data.filter(a => a.level===lvl).length} {lvl==='critical'?'Urgent':lvl==='warning'?'Warning':'Info'}
                    </span>
                  ))}
                </div>
                {alertsQ.data.length === 0 && <div style={{ textAlign:'center', color:'#64748b', padding:40 }}>✅ System healthy — no active alerts</div>}
                {alertsQ.data.map(a => (
                  <div key={a.id} className={`alert-item ${a.level}`}>
                    <div style={{ display:'flex', alignItems:'center', gap:12, flex:1 }}>
                      <AlertBadge level={a.level}/>
                      <span style={{ fontSize:13 }}>{a.message}</span>
                    </div>
                    <span style={{ fontSize:11, color:'#64748b', fontFamily:'IBM Plex Mono,monospace', whiteSpace:'nowrap' }}>
                      {new Date(a.timestamp).toLocaleTimeString()}
                    </span>
                  </div>
                ))}

                <div style={{ background:'#0f172a', border:'1px solid #1e293b', borderRadius:12, padding:20 }}>
                  <h3 style={{ fontSize:14, fontWeight:600, marginBottom:8 }}>📱 SMS Alerts to Village Operator</h3>
                  <p style={{ fontSize:12, color:'#64748b', lineHeight:1.6 }}>
                    When power is low, the system sends an SMS to the village operator on their basic phone — no internet needed.
                    The message is in Hindi so anyone can understand it.
                  </p>
                  <p style={{ fontSize:12, color:'#94a3b8', marginTop:10, fontStyle:'italic' }}>
                    Example SMS: "बिजली कम है। क्लिनिक सुरक्षित है। घर 4-10 बंद हैं। Battery 25%."
                  </p>
                  <p style={{ fontSize:11, color:'#64748b', marginTop:10, fontFamily:'IBM Plex Mono,monospace' }}>
                    Test: POST /api/v1/alerts/sms/test?phone=+91XXXXXXXXXX
                  </p>
                </div>
              </>)}
            </div>
          )}

        </div>
      </main>
    </div>
  )
}

// ── CSS ────────────────────────────────────────────────────────────────────
const CSS = `
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');
  *, *::before, *::after { box-sizing:border-box; margin:0; padding:0; }
  @keyframes spin  { to { transform:rotate(360deg); } }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
  :root { --bg:#020817; --surface:#0f172a; --surface2:#1e293b; --border:#1e293b; --text:#e2e8f0; --muted:#64748b; --accent:#f59e0b; }
  html,body,#root { height:100%; background:var(--bg); color:var(--text); font-family:'Plus Jakarta Sans',sans-serif; }
  .app   { display:flex; height:100vh; overflow:hidden; }
  .sidebar { width:220px; min-width:220px; background:var(--surface); border-right:1px solid var(--border); display:flex; flex-direction:column; padding:20px 12px; gap:8px; }
  .logo  { display:flex; align-items:center; gap:10px; padding:0 8px 20px; border-bottom:1px solid var(--border); }
  .nav   { display:flex; flex-direction:column; gap:4px; flex:1; }
  .nav-btn { display:flex; align-items:center; gap:10px; padding:9px 12px; border-radius:8px; border:none; background:transparent; color:var(--muted); font-size:13px; font-weight:500; cursor:pointer; transition:all .15s; text-align:left; width:100%; }
  .nav-btn:hover  { background:var(--surface2); color:var(--text); }
  .nav-btn.active { background:#f59e0b18; color:#f59e0b; }
  .badge { margin-left:auto; background:#ef4444; color:white; font-size:10px; padding:1px 6px; border-radius:999px; }
  .main   { flex:1; display:flex; flex-direction:column; overflow:hidden; }
  .topbar { display:flex; align-items:center; justify-content:space-between; padding:16px 28px; border-bottom:1px solid var(--border); background:var(--surface); }
  .risk-badge { padding:6px 14px; border-radius:999px; font-size:12px; font-weight:600; }
  .risk-badge.low    { background:#22c55e18; color:#22c55e; }
  .risk-badge.medium { background:#eab30818; color:#eab308; }
  .risk-badge.high   { background:#ef444418; color:#ef4444; }
  .refresh-btn { display:flex; align-items:center; gap:6px; padding:7px 14px; border-radius:8px; border:1px solid var(--border); background:transparent; color:var(--muted); font-size:12px; cursor:pointer; }
  .refresh-btn:hover { color:var(--text); border-color:#f59e0b; }
  .content { flex:1; overflow-y:auto; padding:24px 28px; display:flex; flex-direction:column; gap:16px; }
  .live-bar { display:flex; align-items:center; gap:16px; background:var(--surface); border:1px solid #22c55e30; border-radius:10px; padding:10px 18px; font-size:12px; flex-wrap:wrap; }
  .live-dot { width:8px; height:8px; border-radius:50%; background:#22c55e; animation:pulse 1.5s ease-in-out infinite; flex-shrink:0; }
  .stats-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:16px; }
  .stat-card  { background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:18px; display:flex; flex-direction:column; gap:6px; }
  .stat-icon  { padding:8px; border-radius:8px; display:inline-flex; align-items:center; justify-content:center; width:fit-content; }
  .stat-value { font-size:26px; font-weight:700; font-family:'IBM Plex Mono',monospace; }
  .stat-unit  { font-size:14px; color:var(--muted); font-family:'Plus Jakarta Sans',sans-serif; }
  .stat-label { font-size:12px; color:var(--muted); }
  .stat-sub   { font-size:11px; color:var(--muted); }
  .chart-card  { background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:20px; }
  .chart-title { font-size:14px; font-weight:600; margin-bottom:4px; }
  .chart-desc  { font-size:11px; color:var(--muted); margin-bottom:12px; font-family:'IBM Plex Mono',monospace; }
  .opt-header  { display:flex; align-items:flex-start; justify-content:space-between; background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:20px; gap:16px; }
  .alloc-table  { background:var(--surface); border:1px solid var(--border); border-radius:12px; overflow:hidden; }
  .alloc-header { display:grid; grid-template-columns:2fr 1.2fr 1fr 1fr 1.5fr 1.2fr; gap:12px; padding:12px 20px; background:var(--surface2); font-size:11px; font-weight:600; text-transform:uppercase; letter-spacing:.08em; color:var(--muted); }
  .alloc-row    { display:grid; grid-template-columns:2fr 1.2fr 1fr 1fr 1.5fr 1.2fr; gap:12px; padding:12px 20px; border-top:1px solid var(--border); font-size:13px; align-items:center; }
  .alloc-row:hover { background:var(--surface2); }
  .priority-tag { font-size:10px; padding:3px 8px; border-radius:999px; font-weight:700; font-family:'Plus Jakarta Sans',sans-serif; }
  .priority-tag.critical { background:#ef444420; color:#ef4444; }
  .priority-tag.high     { background:#f9731620; color:#f97316; }
  .priority-tag.normal   { background:#22c55e20; color:#22c55e; }
  .status-tag { font-size:10px; padding:3px 8px; border-radius:999px; font-weight:600; font-family:'Plus Jakarta Sans',sans-serif; }
  .status-tag.full         { background:#22c55e20; color:#22c55e; }
  .status-tag.partial      { background:#eab30820; color:#eab308; }
  .status-tag.critical-low { background:#ef444420; color:#ef4444; }
  .house-card { background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:14px; display:flex; flex-direction:column; gap:8px; }
  .house-card.priority-critical { border-color:#ef444330; }
  .house-card.priority-high     { border-color:#f9731630; }
  .house-top { display:flex; align-items:center; gap:8px; }
  .alert-item { display:flex; justify-content:space-between; align-items:center; background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:14px 18px; gap:12px; }
  .alert-badge { font-size:10px; padding:3px 10px; border-radius:999px; color:white; font-weight:600; white-space:nowrap; }
  .al-count { padding:6px 14px; border-radius:8px; font-size:12px; font-weight:600; }
  .al-count.critical { background:#ef444420; color:#ef4444; }
  .al-count.warning  { background:#f9731620; color:#f97316; }
  .al-count.info     { background:#0ea5e920; color:#0ea5e9; }
`
