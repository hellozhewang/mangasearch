import { useState } from 'react'
import AppBar from '@mui/material/AppBar'
import Autocomplete from '@mui/material/Autocomplete'
import Checkbox from '@mui/material/Checkbox'
import Chip from '@mui/material/Chip'
import IconButton from '@mui/material/IconButton'
import InputAdornment from '@mui/material/InputAdornment'
import ListItemIcon from '@mui/material/ListItemIcon'
import Menu from '@mui/material/Menu'
import MenuItem from '@mui/material/MenuItem'
import TextField from '@mui/material/TextField'
import ToggleButton from '@mui/material/ToggleButton'
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup'
import Toolbar from '@mui/material/Toolbar'
import Typography from '@mui/material/Typography'
import Box from '@mui/material/Box'
import SearchIcon from '@mui/icons-material/Search'
import MenuIcon from '@mui/icons-material/Menu'
import ArticleOutlinedIcon from '@mui/icons-material/ArticleOutlined'
import CircularProgress from '@mui/material/CircularProgress'
import Countdown from './Countdown'
import type { RefreshStatus, StatusFilter } from '../types'

interface Props {
  updated: string
  refreshStatus: RefreshStatus | null
  statusFetchedAt: number
  onOpenLogs: () => void
  query: string
  onQuery: (q: string) => void
  genreCounts: Map<string, number>
  genres: string[]
  onGenres: (g: string[]) => void
  status: StatusFilter
  onStatus: (s: StatusFilter) => void
  shown: number
  total: number
}

export default function FiltersBar(props: Props) {
  const genreOptions = [...props.genreCounts.keys()].sort()
  const [menuAnchor, setMenuAnchor] = useState<HTMLElement | null>(null)

  return (
    <AppBar
      position="sticky"
      color="inherit"
      elevation={0}
      sx={{ borderBottom: 1, borderColor: 'divider', bgcolor: 'background.paper' }}
    >
      <Toolbar sx={{ flexWrap: 'wrap', gap: 1.5, py: 1 }}>
        <IconButton
          edge="start"
          aria-label="menu"
          onClick={(e) => setMenuAnchor(e.currentTarget)}
        >
          <MenuIcon />
        </IconButton>
        <Menu anchorEl={menuAnchor} open={menuAnchor !== null} onClose={() => setMenuAnchor(null)}>
          <MenuItem
            onClick={() => {
              setMenuAnchor(null)
              props.onOpenLogs()
            }}
          >
            <ListItemIcon>
              <ArticleOutlinedIcon fontSize="small" />
            </ListItemIcon>
            Server logs
          </MenuItem>
        </Menu>
        <Box sx={{ mr: 1 }}>
          <Typography variant="h6" component="h1" sx={{ lineHeight: 1.2 }}>
            Manga<Box component="span" sx={{ color: 'primary.main' }}>Search</Box>
          </Typography>
          {props.updated && (
            <Typography variant="caption" color="text.secondary" component="div">
              Updated {props.updated}
              {props.refreshStatus?.running ? (
                <>
                  {' · refreshing '}
                  <CircularProgress size={9} sx={{ ml: 0.25 }} />
                </>
              ) : (
                props.refreshStatus?.next_run != null && (
                  <>
                    {' · next run in '}
                    <Countdown
                      target={props.refreshStatus.next_run}
                      serverTime={props.refreshStatus.server_time}
                      fetchedAt={props.statusFetchedAt}
                    />
                  </>
                )
              )}
            </Typography>
          )}
        </Box>
        <Box sx={{ flexGrow: 1 }} />
        <TextField
          size="small"
          placeholder="Search titles…"
          value={props.query}
          onChange={(e) => props.onQuery(e.target.value)}
          sx={{ width: { xs: '100%', sm: 230 } }}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon fontSize="small" />
              </InputAdornment>
            ),
          }}
        />
        <Autocomplete
          multiple
          size="small"
          disableCloseOnSelect
          options={genreOptions}
          value={props.genres}
          onChange={(_, value) => props.onGenres(value)}
          limitTags={2}
          sx={{ minWidth: 260, maxWidth: 420 }}
          renderOption={(liProps, option, { selected }) => (
            <li {...liProps}>
              <Checkbox size="small" checked={selected} sx={{ mr: 1, p: 0.5 }} />
              {option}
              <Typography variant="caption" color="text.secondary" sx={{ ml: 'auto' }}>
                {props.genreCounts.get(option)}
              </Typography>
            </li>
          )}
          renderTags={(value, getTagProps) =>
            value.map((option, index) => (
              <Chip label={option} size="small" {...getTagProps({ index })} />
            ))
          }
          renderInput={(params) => (
            <TextField {...params} label="Genres (must match all)" placeholder="Filter…" />
          )}
        />
        <ToggleButtonGroup
          exclusive
          size="small"
          value={props.status}
          onChange={(_, v: StatusFilter | null) => v && props.onStatus(v)}
        >
          <ToggleButton value="all">All</ToggleButton>
          <ToggleButton value="completed">Completed</ToggleButton>
          <ToggleButton value="ongoing">Ongoing</ToggleButton>
        </ToggleButtonGroup>
        <Typography variant="body2" color="text.secondary" sx={{ minWidth: 70, textAlign: 'right' }}>
          {props.shown === props.total ? `${props.total} series` : `${props.shown} / ${props.total}`}
        </Typography>
      </Toolbar>
    </AppBar>
  )
}
