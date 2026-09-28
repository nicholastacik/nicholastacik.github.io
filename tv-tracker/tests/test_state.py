from datetime import date

from job.state import active_shows, all_tracked_ids, truthy


def row(**overrides):
    base = {
        "tmdb_id": "1",
        "tvmaze_id": "",
        "name": "One",
        "first_air_year": "2020",
        "poster_url": "p",
        "added_at": "2026-09-20",
        "active": "TRUE",
    }
    return base | overrides


def test_truthy():
    assert truthy("TRUE") and truthy(" true ") and truthy(True)
    assert not truthy("FALSE") and not truthy("") and not truthy("yes")


def test_active_shows_parses_types():
    [show] = active_shows([row(tvmaze_id="44")])
    assert (
        show.tmdb_id,
        show.name,
        show.first_air_year,
        show.added_at,
        show.tvmaze_id,
    ) == (1, "One", 2020, date(2026, 9, 20), 44)


def test_duplicates_collapse_to_earliest_added_and_any_tvmaze_id():
    [show] = active_shows(
        [
            row(added_at="2026-09-22"),
            row(added_at="2026-09-10", tvmaze_id="44"),
            row(added_at="2026-09-01", active="FALSE"),
        ]
    )
    assert show.added_at == date(2026, 9, 10)
    assert show.tvmaze_id == 44


def test_inactive_and_garbage_rows_are_skipped():
    rows = [
        row(active="FALSE"),
        row(tmdb_id=""),
        row(tmdb_id="abc"),
        row(tmdb_id="2", added_at="soon"),
        row(tmdb_id="3", first_air_year=""),
    ]
    assert [(s.tmdb_id, s.first_air_year) for s in active_shows(rows)] == [(3, None)]


def test_all_tracked_ids_includes_inactive():
    assert all_tracked_ids(
        [row(), row(tmdb_id="2", active="FALSE"), row(tmdb_id="")]
    ) == {1, 2}


def test_active_shows_carry_imdb_id():
    [show] = active_shows([row(imdb_id="tt0096697")])
    assert show.imdb_id == "tt0096697"
    [show] = active_shows([row()])
    assert show.imdb_id == ""
