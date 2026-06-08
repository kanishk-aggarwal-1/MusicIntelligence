import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, AreaChart, Area, CartesianGrid,
  LineChart, Line, Legend,
} from 'recharts'
import ErrorBoundary from '../ui/ErrorBoundary'

const COLORS = ['#1db954', '#17a348', '#138d3c', '#0f7030', '#0b5c26']

// Parse a "YYYY-MM" string into a display label without ever constructing a
// Date from a string (which can shift the month in UTC− timezones).
function formatMonth(yyyyMm) {
  if (!yyyyMm) return ''
  const [year, month] = yyyyMm.split('-').map(Number)
  if (!year || !month) return yyyyMm
  // new Date(year, month-1, 1) uses the *local* calendar — no UTC shift.
  return new Date(year, month - 1, 1).toLocaleDateString('en-US', { month: 'short', year: '2-digit' })
}

function pivotTimeline(rows, key) {
  // byMonth is keyed by the raw "YYYY-MM" string so we can sort correctly.
  const byMonth = {}   // "YYYY-MM" → data point object
  const allKeys = new Set()
  for (const row of rows) {
    const iso = (row.month || '').slice(0, 7)   // normalise to "YYYY-MM"
    if (!byMonth[iso]) byMonth[iso] = { month: formatMonth(iso), _iso: iso }
    byMonth[iso][row[key]] = (byMonth[iso][row[key]] || 0) + row.plays
    allKeys.add(row[key])
  }
  // Sort oldest → newest so the x-axis reads left-to-right chronologically.
  const data = Object.values(byMonth)
    .sort((a, b) => a._iso.localeCompare(b._iso))
    .map(({ _iso: _unused, ...rest }) => rest)   // strip the sort key before rendering
  return { data, keys: [...allKeys].slice(0, 5) }
}

function ChartCard({ title, children, empty = 'No data yet', hasData = true, className = '' }) {
  return (
    <ErrorBoundary>
      <div className={`bg-zinc-900 rounded-xl p-5 border border-zinc-800 ${className}`}>
        <h2 className="text-white font-semibold mb-4">{title}</h2>
        {hasData ? children : <p className="text-zinc-500 text-sm">{empty}</p>}
      </div>
    </ErrorBoundary>
  )
}

export default function DashboardCharts({ topArtists, topGenres, hourly, daily, timeline }) {
  return (
    <>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <ChartCard title="Top Artists" hasData={topArtists.length > 0} className="lg:col-span-2">
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={topArtists} layout="vertical" margin={{ left: 8, right: 16 }}>
              <XAxis type="number" tick={{ fill: '#71717a', fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis type="category" dataKey="artist_name" tick={{ fill: '#a1a1aa', fontSize: 11 }} width={90} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ background: '#18181b', border: '1px solid #3f3f46', borderRadius: 8 }} />
              <Bar dataKey="play_count" fill="#1db954" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Top Genres" hasData={topGenres.length > 0} empty="No genre data yet">
          <ResponsiveContainer width="100%" height={160}>
            <PieChart>
              <Pie data={topGenres} dataKey="play_count" nameKey="genre" cx="50%" cy="50%" outerRadius={70} strokeWidth={0}>
                {topGenres.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Pie>
              <Tooltip contentStyle={{ background: '#18181b', border: '1px solid #3f3f46', borderRadius: 8 }} />
            </PieChart>
          </ResponsiveContainer>
          <div className="space-y-1.5 mt-2">
            {topGenres.map((g, i) => (
              <div key={g.genre} className="flex items-center gap-2 text-xs">
                <div className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: COLORS[i % COLORS.length] }} />
                <span className="text-zinc-300 truncate flex-1">{g.genre}</span>
                <span className="text-zinc-500">{g.play_count}</span>
              </div>
            ))}
          </div>
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ChartCard title="Plays by Hour" hasData={hourly.length > 0}>
          <ResponsiveContainer width="100%" height={180}>
            <AreaChart data={hourly}>
              <defs>
                <linearGradient id="hourGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#1db954" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#1db954" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
              <XAxis dataKey="hour" tick={{ fill: '#71717a', fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: '#71717a', fontSize: 10 }} axisLine={false} tickLine={false} width={28} />
              <Tooltip contentStyle={{ background: '#18181b', border: '1px solid #3f3f46', borderRadius: 8 }} />
              <Area type="monotone" dataKey="play_count" stroke="#1db954" fill="url(#hourGrad)" strokeWidth={2} dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Plays by Day" hasData={daily.length > 0}>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={daily}>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
              <XAxis dataKey="day" tick={{ fill: '#71717a', fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: '#71717a', fontSize: 11 }} axisLine={false} tickLine={false} width={28} />
              <Tooltip contentStyle={{ background: '#18181b', border: '1px solid #3f3f46', borderRadius: 8 }} />
              <Bar dataKey="play_count" fill="#1db954" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {timeline && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {(() => {
            const { data, keys } = pivotTimeline(timeline.monthly_top_genres || [], 'genre')
            return (
              <ChartCard title="Genre Timeline" hasData={data.length > 0} empty="Not enough history yet">
                <ResponsiveContainer width="100%" height={200}>
                  <LineChart data={data}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                    <XAxis dataKey="month" tick={{ fill: '#71717a', fontSize: 10 }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fill: '#71717a', fontSize: 10 }} axisLine={false} tickLine={false} width={28} />
                    <Tooltip contentStyle={{ background: '#18181b', border: '1px solid #3f3f46', borderRadius: 8 }} />
                    <Legend wrapperStyle={{ fontSize: 11, color: '#a1a1aa' }} />
                    {keys.map((k, i) => (
                      <Line key={k} type="monotone" dataKey={k} stroke={COLORS[i % COLORS.length]} strokeWidth={2} dot={false} />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </ChartCard>
            )
          })()}
          {(() => {
            const { data, keys } = pivotTimeline(timeline.monthly_top_artists || [], 'artist')
            return (
              <ChartCard title="Artist Timeline" hasData={data.length > 0} empty="Not enough history yet">
                <ResponsiveContainer width="100%" height={200}>
                  <LineChart data={data}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                    <XAxis dataKey="month" tick={{ fill: '#71717a', fontSize: 10 }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fill: '#71717a', fontSize: 10 }} axisLine={false} tickLine={false} width={28} />
                    <Tooltip contentStyle={{ background: '#18181b', border: '1px solid #3f3f46', borderRadius: 8 }} />
                    <Legend wrapperStyle={{ fontSize: 11, color: '#a1a1aa' }} />
                    {keys.map((k, i) => (
                      <Line key={k} type="monotone" dataKey={k} stroke={COLORS[i % COLORS.length]} strokeWidth={2} dot={false} />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </ChartCard>
            )
          })()}
        </div>
      )}
    </>
  )
}
