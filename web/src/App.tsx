import { useCallback, useEffect, useMemo, useState } from 'react'
import useMediaQuery from '@mui/material/useMediaQuery'
import { ThemeProvider, createTheme } from '@mui/material/styles'
import CssBaseline from '@mui/material/CssBaseline'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import CircularProgress from '@mui/material/CircularProgress'
import Container from '@mui/material/Container'
import Snackbar from '@mui/material/Snackbar'
import Countdown from './components/Countdown'
import DescriptionDialog from './components/DescriptionDialog'
import FiltersBar from './components/FiltersBar'
import LogsDialog from './components/LogsDialog'
import SeriesTable from './components/SeriesTable'
import type { DataPayload, MuList, RefreshStatus, SeriesRecord, SortKey, StatusFilter } from './types'

export default function App() {
  const prefersDark = useMediaQuery('(prefers-color-scheme: dark)')
  const theme = useMemo(
    () =>
      createTheme({
        palette: {
          mode: prefersDark ? 'dark' : 'light',
          primary: { main: prefersDark ? '#a29bfe' : '#6c5ce7' },
        },
        shape: { borderRadius: 10 },
      }),
    [prefersDark],
  )

  const [payload, setPayload] = useState<DataPayload | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [lists, setLists] = useState<MuList[] | null>(null)

  const [query, setQuery] = useState('')
  // The backend searches all genres; Romance is just the default lens.
  const [genres, setGenres] = useState<string[]>(['Romance'])
  const [status, setStatus] = useState<StatusFilter>('all')
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: 'rank', dir: 1 })
  const [added, setAdded] = useState<Record<number, string>>({})
  const [toast, setToast] = useState<string | null>(null)
  const [descRecord, setDescRecord] = useState<SeriesRecord | null>(null)
  const [logsOpen, setLogsOpen] = useState(false)

  const [refreshStatus, setRefreshStatus] = useState<RefreshStatus | null>(null)
  const [statusFetchedAt, setStatusFetchedAt] = useState(0)

  useEffect(() => {
    fetch('/api/records')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((j: DataPayload) => setPayload(j))
      .catch((e: Error) => setLoadError(`Could not load records (${e.message})`))
  }, [])

  useEffect(() => {
    // No backend (e.g. page opened as a bare file): lists stay null and the
    // Add-to column is simply not rendered.
    fetch('/api/lists')
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((j: { lists: MuList[] }) => setLists(j.lists))
      .catch(() => setLists(null))
  }, [])

  // Poll refresh status every 30 s; tick a local clock for the countdown.
  useEffect(() => {
    const poll = () =>
      fetch('/api/status')
        .then((r) => (r.ok ? r.json() : Promise.reject()))
        .then((j: RefreshStatus) => {
          setRefreshStatus(j)
          setStatusFetchedAt(Date.now() / 1000)
        })
        .catch(() => setRefreshStatus(null))
    poll()
    const id = setInterval(poll, 30_000)
    return () => clearInterval(id)
  }, [])

  // When an hourly refresh lands, pull the new data without a page reload.
  const lastSuccess = refreshStatus?.last_success
  useEffect(() => {
    if (!lastSuccess) return
    fetch('/api/records')
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((j: DataPayload) => setPayload(j))
      .catch(() => {})
  }, [lastSuccess])

  const records = payload?.records ?? []

  const genreCounts = useMemo(() => {
    const counts = new Map<string, number>()
    for (const r of records) {
      for (const g of r.genres) counts.set(g, (counts.get(g) ?? 0) + 1)
    }
    return counts
  }, [records])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return records.filter((r) => {
      if (q && !r.title.toLowerCase().includes(q)) return false
      // AND semantics: the series must carry every selected genre.
      if (!genres.every((g) => r.genres.includes(g))) return false
      if (status === 'completed' && !r.completed) return false
      if (status === 'ongoing' && r.completed) return false
      return true
    })
  }, [records, query, genres, status])

  const sorted = useMemo(() => {
    const cmp = (a: SeriesRecord, b: SeriesRecord): number => {
      const ka = a[sort.key]
      const kb = b[sort.key]
      if (typeof ka === 'string' && typeof kb === 'string') return ka.localeCompare(kb)
      return (ka as number) - (kb as number)
    }
    return [...filtered].sort((a, b) => cmp(a, b) * sort.dir)
  }, [filtered, sort])

  // Stable callbacks so the memoized rows don't re-render on unrelated state.
  const handleSort = useCallback((key: SortKey) => {
    setSort((cur) =>
      cur.key === key
        ? { key, dir: cur.dir === 1 ? -1 : 1 }
        : { key, dir: key === 'title' || key === 'rank' ? 1 : -1 },
    )
  }, [])

  const toggleGenre = useCallback(
    (g: string) => setGenres((cur) => (cur.includes(g) ? cur.filter((x) => x !== g) : [...cur, g])),
    [],
  )

  const showDescription = useCallback((record: SeriesRecord) => setDescRecord(record), [])
  const closeDescription = useCallback(() => setDescRecord(null), [])
  const openLogs = useCallback(() => setLogsOpen(true), [])
  const closeLogs = useCallback(() => setLogsOpen(false), [])

  const addToList = useCallback(async (record: SeriesRecord, list: MuList) => {
    const resp = await fetch('/api/list', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ series_id: record.id, list_id: list.id }),
    })
    const body = await resp.json().catch(() => ({}))
    if (!resp.ok) {
      setToast(`Could not add "${record.title}" to ${list.title}: ${body.error ?? resp.status}`)
      return
    }
    const label = list.icon ? `${list.icon} ${list.title}` : list.title
    setAdded((cur) => ({ ...cur, [record.id]: label }))
  }, [])

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <FiltersBar
        updated={payload?.updated ?? ''}
        refreshStatus={refreshStatus}
        statusFetchedAt={statusFetchedAt}
        onOpenLogs={openLogs}
        query={query}
        onQuery={setQuery}
        genreCounts={genreCounts}
        genres={genres}
        onGenres={setGenres}
        status={status}
        onStatus={setStatus}
        shown={sorted.length}
        total={records.length}
      />
      <Container maxWidth={false} sx={{ maxWidth: 1500, py: 2 }}>
        {loadError && <Alert severity="error">{loadError}</Alert>}
        {refreshStatus?.last_error && (
          <Alert severity="warning" sx={{ mb: 2 }}>
            Last refresh failed
            {refreshStatus.last_error_at &&
              ` at ${new Date(refreshStatus.last_error_at * 1000).toLocaleTimeString()}`}
            : {refreshStatus.last_error} — retrying automatically
            {refreshStatus.next_run != null && (
              <>
                {' in '}
                <Countdown
                  target={refreshStatus.next_run}
                  serverTime={refreshStatus.server_time}
                  fetchedAt={statusFetchedAt}
                />
              </>
            )}
            .
          </Alert>
        )}
        {!payload && !loadError && (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
            <CircularProgress />
          </Box>
        )}
        {payload && (
          <SeriesTable
            records={sorted}
            sortKey={sort.key}
            sortDir={sort.dir}
            onSort={handleSort}
            selectedGenres={genres}
            onToggleGenre={toggleGenre}
            lists={lists}
            added={added}
            onAdd={addToList}
            onShowDescription={showDescription}
          />
        )}
      </Container>
      <DescriptionDialog record={descRecord} onClose={closeDescription} />
      <LogsDialog open={logsOpen} onClose={closeLogs} />
      <Snackbar
        open={toast !== null}
        autoHideDuration={6000}
        onClose={() => setToast(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert severity="error" variant="filled" onClose={() => setToast(null)}>
          {toast}
        </Alert>
      </Snackbar>
    </ThemeProvider>
  )
}
