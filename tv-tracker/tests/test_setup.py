from datetime import datetime

from fakes import FakeTmdb
from job.config import TZ
from job.setup import import_rows


def test_import_rows_skips_existing_and_fetches_posters():
    tmdb = FakeTmdb({1: {"poster_path": "/p1.jpg"}, 2: {"poster_path": None}})
    shows = [
        {"tmdb_id": 1, "name": "One", "first_air_year": 2020},
        {"tmdb_id": 2, "name": "Two", "first_air_year": 2021},
        {"tmdb_id": 3, "name": "Three", "first_air_year": 2022},
        {"tmdb_id": 1, "name": "One again", "first_air_year": 2020},
    ]
    rows = import_rows(
        shows, [{"tmdb_id": "3"}], tmdb, datetime(2026, 9, 28, 7, 0, tzinfo=TZ)
    )
    assert rows == [
        {
            "tmdb_id": 1,
            "tvmaze_id": "",
            "name": "One",
            "first_air_year": 2020,
            "poster_url": "https://image.tmdb.org/t/p/w342/p1.jpg",
            "added_at": "2026-09-28",
            "source": "import",
            "active": True,
            "updated_at": "2026-09-28T07:00:00-04:00",
        },
        {
            "tmdb_id": 2,
            "tvmaze_id": "",
            "name": "Two",
            "first_air_year": 2021,
            "poster_url": "",
            "added_at": "2026-09-28",
            "source": "import",
            "active": True,
            "updated_at": "2026-09-28T07:00:00-04:00",
        },
    ]
