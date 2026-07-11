import Box from '@mui/material/Box'
import Chip from '@mui/material/Chip'
import Dialog from '@mui/material/Dialog'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import IconButton from '@mui/material/IconButton'
import Link from '@mui/material/Link'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import useMediaQuery from '@mui/material/useMediaQuery'
import { useTheme } from '@mui/material/styles'
import CloseIcon from '@mui/icons-material/Close'
import type { SeriesRecord } from '../types'

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
          </DialogContent>
        </>
      )}
    </Dialog>
  )
}
