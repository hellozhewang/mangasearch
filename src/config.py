"""Shared configuration: paths, search filters, refresh TTLs, scoring weights."""

from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SRC_DIR.parent

DB_PATH = PROJECT_ROOT / 'data' / 'mangasearch.db'
LOG_DIR = PROJECT_ROOT / 'logs'

SEARCH_RESULTS_TTL_SECS = 300
REQUEST_DELAY_SECS = 0.75
REFRESH_INTERVAL_SECS = 3600
TOP_N = 300
# Slightly below the old 6.8: with taste weights up to ~+0.5, a well-fitting
# 6.6 can now legitimately compete for the bottom of the top-150.
MIN_RATING = 6.6

DAY = 3600 * 24
# TTLs are jittered per entry so refreshes stay spread out over time.
TTL = {
    'series': (15 * DAY, 25 * DAY),
    'rating': (25 * DAY, 40 * DAY),
    'comments': (1 * DAY, 2 * DAY),
}

SEARCH = {
    # MU silently caps search paging at ~3900 results per query, so one
    # all-genre pass only reaches down to ~7.0. Each pass gets its own window:
    # [] = all genres (breadth), ['Romance'] = deep Romance coverage (the
    # frontend's default filter). Results are merged and deduped.
    'genre_passes': [[], ['Romance']],
    'exclude_genres': ['Shotacon', 'Shoujo Ai', 'Shounen Ai', 'Yaoi', 'Yuri', 'Hentai'],
    'types': ['Manga', 'Manhwa', 'Manhua'],
}

SCORING = {
    # "8Club": exceptional ratings (ramped 7.75 -> 8.25) mostly buy forgiveness
    # of the age penalty — a 15-year-old 8.3 deserves attention, a 15-year-old
    # 6.9 does not — plus a small flat nudge.
    'high_rating_ramp_start': 7.75,
    'high_rating_ramp_end': 8.25,
    'high_rating_bonus': 0.15,
    'high_rating_year_forgiveness': 0.8,  # share of year penalty waived at full ramp
    'high_rating_forgiveness_cap': 1.0,   # ... but never more than this much

    # Trending: credit low-vote upside vs the conservative bayesian rating.
    # Fades linearly to zero by hype_fade_votes (no cliff) and is capped so a
    # 12-vote darling can't steamroll proven series.
    'hype_fade_votes': 60,
    'hype_cap': 0.6,
    'hype_gravity': 17,
    'global_mean': 6.40,

    # Recency: penalize series older than the rolling window, capped.
    'recency_window_years': 6,
    'year_penalty_per_year': 1 / 9,
    'year_penalty_cap': 2.5,

    # Taste weights, ~3x the original values so they shape the ranking
    # instead of merely breaking ties.
    'genre_weights': {
        'Seinen': 0.30,
        'Shounen': 0.075,
        'Josei': 0.15,
        'Adult': 0.075,
        'Shoujo': -0.30,
        'Harem': -0.30,
    },

    # Flat category bonuses (the old base+per-vote formulas hit their caps at
    # a single vote, so they were binary flags in disguise).
    'category_bonuses': {
        'Fast Romance': 0.10,
        'Beautiful Artwork': 0.06,
    },
    'couple_bonus': 0.12,

    'completed_bonus': 0.25,
}
