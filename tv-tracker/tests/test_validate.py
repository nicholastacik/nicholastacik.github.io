from job.validate import pick_match, resolve_suggestions

SHOGUN_1980 = {
    "id": 1,
    "name": "Shōgun",
    "original_name": "Shōgun",
    "first_air_date": "1980-09-15",
    "poster_path": "/a.jpg",
}
SHOGUN_2024 = {
    "id": 2,
    "name": "Shōgun",
    "original_name": "Shōgun",
    "first_air_date": "2024-02-27",
    "poster_path": "/b.jpg",
}
OTHER = {"id": 3, "name": "Shōgun Assassin", "first_air_date": "2024-01-01"}


def test_pick_match_uses_year_not_first_result():
    assert pick_match([SHOGUN_1980, SHOGUN_2024], "Shōgun", 2024)["id"] == 2


def test_pick_match_allows_one_year_off_but_prefers_exact():
    assert pick_match([SHOGUN_2024], "shōgun", 2023)["id"] == 2
    near = {**SHOGUN_2024, "id": 9, "first_air_date": "2025-01-01"}
    assert pick_match([near, SHOGUN_2024], "Shōgun", 2024)["id"] == 2


def test_pick_match_rejects_title_mismatch_and_far_years():
    assert pick_match([OTHER], "Shōgun", 2024) is None
    assert pick_match([SHOGUN_1980], "Shōgun", 2024) is None
    assert (
        pick_match([{"id": 4, "name": "Shōgun", "first_air_date": ""}], "Shōgun", 2024)
        is None
    )


def test_pick_match_accepts_original_name():
    show = {
        "id": 5,
        "name": "Money Heist",
        "original_name": "La casa de papel",
        "first_air_date": "2017-05-02",
    }
    assert pick_match([show], "La Casa de Papel", 2017)["id"] == 5


def test_resolve_keeps_confirmed_and_drops_with_reasons():
    results = {"Shōgun": [SHOGUN_1980, SHOGUN_2024], "Made Up Show": []}
    raw = [
        {
            "title": "Shōgun",
            "year": 2024,
            "reason": "Like Severance, it's slow and tense.",
        },
        {"title": "Made Up Show", "year": 2025, "reason": "x"},
    ]
    kept, dropped = resolve_suggestions(raw, results.__getitem__, known_ids=set())
    assert len(kept) == 1
    s = kept[0]
    assert (s.tmdb_id, s.name, s.year) == (2, "Shōgun", 2024)
    assert s.reason == "Like Severance, it's slow and tense."
    assert s.poster_url == "https://image.tmdb.org/t/p/w342/b.jpg"
    assert s.link == "https://www.themoviedb.org/tv/2"
    assert dropped == ["Made Up Show (2025): no TMDB match"]


def test_resolve_drops_known_and_in_batch_duplicates():
    raw = [
        {"title": "Shōgun", "year": 2024, "reason": "a"},
        {"title": "Shōgun", "year": 2024, "reason": "b"},
    ]
    kept, dropped = resolve_suggestions(
        raw, lambda title: [SHOGUN_2024], known_ids=set()
    )
    assert [s.reason for s in kept] == ["a"]
    assert dropped == ["Shōgun (2024): already tracked, ignored or suggested"]

    kept, dropped = resolve_suggestions(
        raw[:1], lambda title: [SHOGUN_2024], known_ids={2}
    )
    assert kept == []
    assert len(dropped) == 1
