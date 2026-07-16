import { memo, useState } from 'react'
import Box from '@mui/material/Box'
import Chip from '@mui/material/Chip'
import Link from '@mui/material/Link'
import MenuItem from '@mui/material/MenuItem'
import Select from '@mui/material/Select'
import Stack from '@mui/material/Stack'
import TableCell from '@mui/material/TableCell'
import TableRow from '@mui/material/TableRow'
import Typography from '@mui/material/Typography'
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
import type { MuList, SeriesRecord } from '../types'

interface Props {
  record: SeriesRecord
  selectedGenres: string[]
  onToggleGenre: (g: string) => void
  lists: MuList[] | null
  listedListId?: number
  onAdd: (record: SeriesRecord, list: MuList) => void
  onShowDescription: (record: SeriesRecord) => void
}

const searchUrl = (engine: 'google' | 'duck' | 'yandex', title: string) => {
  const q = encodeURIComponent(`read ${title}`)
  if (engine === 'google') return `https://www.google.com/search?q=${q}`
  if (engine === 'duck') return `https://duckduckgo.com/?q=${q}`
  return `https://yandex.com/search/?text=${q}`
}

// memo: with 150 rows of ~30 MUI components each, re-rendering all rows on
// every app-level state tick is what made the page crawl.
export default memo(function SeriesRow(props: Props) {
  const { record: r } = props
  const [pending, setPending] = useState(false)

  return (
    <>
      <TableRow
        hover
        onClick={() => props.onShowDescription(r)}
        sx={{ cursor: 'pointer', ...(props.listedListId != null && { opacity: 0.55 }) }}
      >
        <TableCell sx={{ py: 0.75 }}>
          {r.image && (
            <Box
              component="img"
              src={r.image}
              alt=""
              loading="lazy"
              sx={{ width: 100, height: 142, objectFit: 'cover', borderRadius: 1, display: 'block' }}
            />
          )}
        </TableCell>
        <TableCell sx={{ maxWidth: 240 }}>
          <Stack direction="row" alignItems="center" spacing={0.5}>
            <InfoOutlinedIcon fontSize="inherit" color="disabled" />
            <Link
              href={r.url}
              target="_blank"
              rel="noopener"
              underline="hover"
              color="inherit"
              fontWeight={600}
              onClick={(e) => e.stopPropagation()}
            >
              {r.title}
            </Link>
          </Stack>
          <Stack direction="row" spacing={1} sx={{ mt: 0.25, pl: 2.5 }}>
            {(['google', 'duck', 'yandex'] as const).map((engine) => (
              <Link
                key={engine}
                href={searchUrl(engine, r.title)}
                target="_blank"
                rel="noopener"
                variant="caption"
                color="text.secondary"
                underline="hover"
                onClick={(e) => e.stopPropagation()}
              >
                {engine}
              </Link>
            ))}
          </Stack>
        </TableCell>
        <TableCell>{r.year}</TableCell>
        <TableCell sx={{ maxWidth: 210 }}>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
            {r.genres.map((g) => (
              <Chip
                key={g}
                label={g}
                size="small"
                color={props.selectedGenres.includes(g) ? 'primary' : 'default'}
                variant={props.selectedGenres.includes(g) ? 'filled' : 'outlined'}
                onClick={(e) => {
                  e.stopPropagation()
                  props.onToggleGenre(g)
                }}
              />
            ))}
          </Box>
        </TableCell>
        <TableCell sx={{ maxWidth: 180 }}>
          <Typography variant="caption" color="text.secondary">
            {r.status}
          </Typography>
        </TableCell>
        <TableCell align="right">
          <Typography variant="body2" fontWeight={600}>
            {r.bayesian.toFixed(2)}
          </Typography>
          <Typography variant="caption" color="text.secondary" component="div" sx={{ whiteSpace: 'nowrap' }}>
            avg {r.average ? r.average.toFixed(2) : '—'}
          </Typography>
          <Typography variant="caption" color="text.secondary" component="div" sx={{ whiteSpace: 'nowrap' }}>
            {r.votes} votes
          </Typography>
        </TableCell>
        <TableCell align="right">
          <Typography fontWeight={700} color="primary">
            {r.score.toFixed(2)}
          </Typography>
        </TableCell>
        <TableCell sx={{ maxWidth: 200 }}>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
            {Object.entries(r.breakdown).map(([k, v]) => (
              <Chip
                key={k}
                label={`${k} ${v >= 0 ? '+' : ''}${v.toFixed(2)}`}
                size="small"
                variant="outlined"
                color={v >= 0 ? 'success' : 'error'}
                sx={{ fontSize: 11, height: 20 }}
              />
            ))}
          </Box>
        </TableCell>
        {props.lists && (
          <TableCell onClick={(e) => e.stopPropagation()} sx={{ minWidth: 140, opacity: 1 }}>
            {/* Shows the list this series is on; changing it moves the series
                on MangaUpdates. Listed rows dim until the hourly refresh
                sweeps them out of the candidate pool. */}
            <Select
              size="small"
              value={props.listedListId ?? ''}
              displayEmpty
              disabled={pending}
              fullWidth
              onChange={async (e) => {
                const list = props.lists!.find((l) => l.id === Number(e.target.value))
                if (!list) return
                setPending(true)
                await props.onAdd(r, list)
                setPending(false)
              }}
            >
              <MenuItem value="" disabled>
                Select…
              </MenuItem>
              {props.lists.map((l) => (
                <MenuItem key={l.id} value={l.id}>
                  {l.icon ? `${l.icon} ${l.title}` : l.title}
                </MenuItem>
              ))}
            </Select>
          </TableCell>
        )}
      </TableRow>
    </>
  )
})
