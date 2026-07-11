export interface SeriesRecord {
  rank: number
  id: number
  title: string
  url: string
  image: string
  year: string
  genres: string[]
  status: string
  description: string
  completed: boolean
  votes: number
  bayesian: number
  average: number
  score: number
  breakdown: Record<string, number>
}

export interface DataPayload {
  updated: string
  records: SeriesRecord[]
}

export interface MuList {
  id: number
  title: string
  icon: string
  custom: boolean
}

export type SortKey = 'rank' | 'title' | 'year' | 'votes' | 'bayesian' | 'average' | 'score'
export type StatusFilter = 'all' | 'completed' | 'ongoing'

export interface RefreshStatus {
  running: boolean
  last_success: number | null
  last_error: string | null
  last_error_at: number | null
  next_run: number | null
  server_time: number
}
