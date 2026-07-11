"""Shared configuration: paths, search filters, refresh TTLs, scoring weights."""

from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SRC_DIR.parent

DB_PATH = PROJECT_ROOT / 'data' / 'mangasearch.db'
TEMPLATE_PATH = PROJECT_ROOT / 'templates' / 'template.html'
OUTPUT_PATH = PROJECT_ROOT / 'docs' / 'index.html'

# Legacy pickle caches — imported into SQLite once, then no longer touched.
LEGACY_PICKLES = {
    'search': PROJECT_ROOT / 'cache.pickle',
    'series': PROJECT_ROOT / 'series_cache.pickle',
    'rating': PROJECT_ROOT / 'rating_cache.pickle',
}

SEARCH_RESULTS_TTL_SECS = 300
REQUEST_DELAY_SECS = 0.75

DAY = 3600 * 24
# TTLs are jittered per entry so refreshes stay spread out over time.
TTL = {
    'series': (15 * DAY, 25 * DAY),
    'rating': (25 * DAY, 40 * DAY),
}

SEARCH = {
    'genres': ['Romance'],
    'exclude_genres': ['Shotacon', 'Shoujo Ai', 'Shounen Ai', 'Yaoi', 'Yuri', 'Hentai'],
    'types': ['Manga', 'Manhwa', 'Manhua'],
}

SCORING = {
    # Graded bonus for very highly rated series. Ramps linearly from 0 at 7.75
    # to the full bonus at 8.25 (the old version was a hard +0.5 cliff at 8.00,
    # so a 7.99 series scored half a point below an 8.00 one).
    'high_rating_ramp_start': 7.75,
    'high_rating_ramp_end': 8.25,
    'high_rating_bonus': 0.5,

    # "Trending" boost for low-vote series: blend the raw average toward the
    # site-wide mean with a small prior, and credit any upside vs the
    # (conservative) bayesian rating.
    'hype_votes_threshold': 30,
    'hype_gravity': 17,
    'global_mean': 6.40,

    # Recency: penalize series older than the rolling window, capped.
    'recency_window_years': 6,
    'year_penalty_per_year': 1 / 9,
    'year_penalty_cap': 2.5,

    'genre_weights': {
        'Seinen': 0.10,
        'Shounen': 0.025,
        'Josei': 0.05,
        'Adult': 0.025,
        'Shoujo': -0.10,
        'Harem': -0.10,
    },

    # Category bonuses: base + per_vote * votes_plus, capped.
    'category_bonuses': {
        'Fast Romance': {'base': 0.02, 'per_vote': 0.02, 'cap': 0.05},
        'Beautiful Artwork': {'base': 0.01, 'per_vote': 0.01, 'cap': 0.05},
    },
    'couple_base': 0.02,
    'couple_per_vote': 0.02,
    'couple_cap': 0.08,

    'completed_bonus': 0.125,
}
