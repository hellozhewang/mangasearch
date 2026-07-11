import { useCallback, useEffect, useRef, useState } from 'react'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import CircularProgress from '@mui/material/CircularProgress'
import Dialog from '@mui/material/Dialog'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import IconButton from '@mui/material/IconButton'
import useMediaQuery from '@mui/material/useMediaQuery'
import { useTheme } from '@mui/material/styles'
import CloseIcon from '@mui/icons-material/Close'
import RefreshIcon from '@mui/icons-material/Refresh'

interface Props {
  open: boolean
  onClose: () => void
}

function lineColor(line: string): string | undefined {
  if (line.includes(' ERROR ') || line.includes('Traceback')) return 'error.main'
  if (line.includes(' WARNING ')) return 'warning.main'
  return undefined
}

export default function LogsDialog({ open, onClose }: Props) {
  const theme = useTheme()
  const fullScreen = useMediaQuery(theme.breakpoints.down('sm'))
  const [lines, setLines] = useState<string[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  const load = useCallback(() => {
    fetch('/api/logs?lines=300')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((j: { lines: string[] }) => setLines(j.lines))
      .catch((e: Error) => setError(`Could not load logs (${e.message})`))
  }, [])

  useEffect(() => {
    if (open) {
      setLines(null)
      setError(null)
      load()
    }
  }, [open, load])

  // Newest entries are at the end — start scrolled to the bottom.
  useEffect(() => {
    bottomRef.current?.scrollIntoView()
  }, [lines])

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md" fullScreen={fullScreen}>
      <DialogTitle sx={{ pr: 12 }}>
        Server logs
        <IconButton onClick={load} sx={{ position: 'absolute', right: 48, top: 8 }} aria-label="reload logs">
          <RefreshIcon />
        </IconButton>
        <IconButton onClick={onClose} sx={{ position: 'absolute', right: 8, top: 8 }} aria-label="close">
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers sx={{ bgcolor: 'background.default' }}>
        {error && <Alert severity="error">{error}</Alert>}
        {!lines && !error && (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
            <CircularProgress size={28} />
          </Box>
        )}
        {lines && (
          <Box sx={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontSize: 12, lineHeight: 1.5 }}>
            {lines.length === 0 && (
              <Box sx={{ color: 'text.secondary', fontStyle: 'italic' }}>Log file is empty.</Box>
            )}
            {lines.map((l, i) => (
              <Box key={i} sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all', color: lineColor(l) }}>
                {l}
              </Box>
            ))}
            <div ref={bottomRef} />
          </Box>
        )}
      </DialogContent>
    </Dialog>
  )
}
