import { useEffect, useState } from 'react'
import Box from '@mui/material/Box'
import Chip from '@mui/material/Chip'
import CircularProgress from '@mui/material/CircularProgress'
import Dialog from '@mui/material/Dialog'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import Divider from '@mui/material/Divider'
import IconButton from '@mui/material/IconButton'
import Link from '@mui/material/Link'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import useMediaQuery from '@mui/material/useMediaQuery'
import { useTheme } from '@mui/material/styles'
import CloseIcon from '@mui/icons-material/Close'
import type { SeriesRecord } from '../types'

interface Comment {
  author: string
  content: string
  useful: number
  rating: number | null
  time: string
}

interface Props {
  record: SeriesRecord | null
  onClose: () => void
}

/** Description shown as an overlay (full-screen sheet on phones) so opening it
 *  never changes the table's geometry — inline expansion forced the browser to
 *  re-rasterize everything below the row, freezing scroll on large tables. */
export default function DescriptionDialog({ record: r, onClose }: Props) {
  const theme = useTheme()
  const fullScreen = useMediaQuery(theme.breakpoints.down('sm'))

  const seriesId = r?.id
  const [comments, setComments] = useState<Comment[] | null>(null)
  const [commentsAvailable, setCommentsAvailable] = useState(true)

  useEffect(() => {
    if (!seriesId) return
    setComments(null)
    setCommentsAvailable(true)
    fetch(`/api/comments?series=${seriesId}`)
      .then((res) => (res.ok ? res.json() : Promise.reject()))
      .then((j: { comments: Comment[] }) => setComments(j.comments))
      .catch(() => setCommentsAvailable(false))
  }, [seriesId])

  return (
    <Dialog open={r !== null} onClose={onClose} fullWidth maxWidth="sm" fullScreen={fullScreen}>
      {r && (
        <>
          <DialogTitle sx={{ pr: 6 }}>
            <Stack direction="row" spacing={2} alignItems="center">
              {r.image && (
                <Box
                  component="img"
                  src={r.image}
                  alt=""
                  sx={{ width: 44, height: 62, objectFit: 'cover', borderRadius: 1 }}
                />
              )}
              <Box>
                <Link href={r.url} target="_blank" rel="noopener" underline="hover" color="inherit">
                  {r.title}
                </Link>
                <Typography variant="body2" color="text.secondary">
                  {r.year} · {r.votes} votes · score {r.score.toFixed(2)}
                </Typography>
              </Box>
            </Stack>
            <IconButton onClick={onClose} sx={{ position: 'absolute', right: 8, top: 8 }} aria-label="close">
              <CloseIcon />
            </IconButton>
          </DialogTitle>
          <DialogContent dividers>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mb: 1.5 }}>
              {r.genres.map((g) => (
                <Chip key={g} label={g} size="small" variant="outlined" />
              ))}
            </Box>
            <Typography
              variant="body2"
              sx={{ whiteSpace: 'pre-line', fontStyle: r.description ? 'normal' : 'italic' }}
            >
              {r.description || 'No description on MangaUpdates.'}
            </Typography>
            {commentsAvailable && (
              <>
                <Divider sx={{ my: 2 }} />
                <Typography variant="subtitle2" sx={{ mb: 1.5 }}>
                  Recent comments{comments && comments.length > 0 && ` (${comments.length})`}
                </Typography>
                {!comments && (
                  <Box sx={{ display: 'flex', justifyContent: 'center', py: 3 }}>
                    <CircularProgress size={22} />
                  </Box>
                )}
                {comments && comments.length === 0 && (
                  <Typography variant="body2" color="text.secondary" fontStyle="italic">
                    No comments yet.
                  </Typography>
                )}
                {comments?.map((c, i) => (
                  <Box key={i} sx={{ mb: 2 }}>
                    <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.25 }}>
                      <Typography variant="body2" fontWeight={600}>
                        {c.author}
                      </Typography>
                      {c.rating != null && (
                        <Chip label={`★ ${c.rating}`} size="small" color="primary" variant="outlined" sx={{ height: 18, fontSize: 11 }} />
                      )}
                      {c.useful > 0 && (
                        <Chip label={`+${c.useful} useful`} size="small" variant="outlined" sx={{ height: 18, fontSize: 11 }} />
                      )}
                      <Typography variant="caption" color="text.secondary">
                        {c.time}
                      </Typography>
                    </Stack>
                    <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: 'pre-line' }}>
                      {c.content}
                    </Typography>
                  </Box>
                ))}
              </>
            )}
          </DialogContent>
        </>
      )}
    </Dialog>
  )
}
