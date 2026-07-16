import { memo } from 'react'
import Paper from '@mui/material/Paper'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableContainer from '@mui/material/TableContainer'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import TableSortLabel from '@mui/material/TableSortLabel'
import Typography from '@mui/material/Typography'
import SeriesRow from './SeriesRow'
import type { MuList, SeriesRecord, SortKey } from '../types'

interface Props {
  records: SeriesRecord[]
  sortKey: SortKey
  sortDir: 1 | -1
  onSort: (key: SortKey) => void
  selectedGenres: string[]
  onToggleGenre: (g: string) => void
  lists: MuList[] | null
  listed: Record<number, number>
  onAdd: (record: SeriesRecord, list: MuList) => void
  onShowDescription: (record: SeriesRecord) => void
}

const COLUMNS: { key?: SortKey; label: string; align?: 'right'; width: number }[] = [
  { label: '', width: 116 }, // cover
  { key: 'title', label: 'Title', width: 240 },
  { key: 'year', label: 'Year', width: 64 },
  { label: 'Genres', width: 220 },
  { label: 'Status', width: 150 },
  { key: 'bayesian', label: 'Rating', align: 'right', width: 110 },
  { key: 'score', label: 'Score', align: 'right', width: 80 },
  { label: 'Why', width: 210 },
]

export default memo(function SeriesTable(props: Props) {
  return (
    <TableContainer component={Paper} variant="outlined">
      {/* tableLayout fixed: with 150 rows, auto layout re-measures every cell
          on any height change (row expand, image load) — that was the CPU spike. */}
      <Table size="small" stickyHeader sx={{ minWidth: 1050, tableLayout: 'fixed' }}>
        <colgroup>
          {COLUMNS.map((col) => (
            <col key={col.label || 'cover'} style={{ width: col.width }} />
          ))}
          {props.lists && <col style={{ width: 150 }} />}
        </colgroup>
        <TableHead>
          <TableRow>
            {COLUMNS.map((col) => (
              <TableCell key={col.label || 'cover'} align={col.align}>
                {col.key ? (
                  <TableSortLabel
                    active={props.sortKey === col.key}
                    direction={props.sortDir === 1 ? 'asc' : 'desc'}
                    onClick={() => props.onSort(col.key!)}
                  >
                    {col.label}
                  </TableSortLabel>
                ) : (
                  col.label
                )}
              </TableCell>
            ))}
            {props.lists && <TableCell>List</TableCell>}
          </TableRow>
        </TableHead>
        <TableBody>
          {props.records.map((r) => (
            <SeriesRow
              key={r.id}
              record={r}
              selectedGenres={props.selectedGenres}
              onToggleGenre={props.onToggleGenre}
              lists={props.lists}
              listedListId={props.listed[r.id]}
              onAdd={props.onAdd}
              onShowDescription={props.onShowDescription}
            />
          ))}
        </TableBody>
      </Table>
      {props.records.length === 0 && (
        <Typography sx={{ p: 5, textAlign: 'center' }} color="text.secondary">
          No matches.
        </Typography>
      )}
    </TableContainer>
  )
})
