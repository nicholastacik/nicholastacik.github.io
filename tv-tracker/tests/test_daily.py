from datetime import datetime
from types import SimpleNamespace as NS

from fakes import FakeLlm, FakeTmdb, FakeTvmaze, get_cell, make_spreadsheet, set_cell
from job.config import TZ
from job.daily import run_daily
from job.sheet import Sheet

NOW = datetime(2026, 9, 28, 6, 0, tzinfo=TZ)  # Monday


def tracked(tmdb_id, name, added_at="2026-09-20", tvmaze_id=""):
    return {
        "tmdb_id": tmdb_id,
        "tvmaze_id": tvmaze_id,
        "name": name,
        "first_air_year": 2020,
        "poster_url": "",
        "added_at": added_at,
        "source": "import",
        "active": True,
    }


def show_json(tmdb_id, name, seasons, next_episode=None):
    return {
        "id": tmdb_id,
        "name": name,
        "poster_path": f"/p{tmdb_id}.jpg",
        "external_ids": {"imdb_id": f"tt{tmdb_id}"},
        "seasons": seasons,
        "next_episode_to_air": next_episode,
    }


def episodes(*rows):
    return {
        "episodes": [
            {
                "season_number": s,
                "episode_number": e,
                "name": n,
                "air_date": d,
                "still_path": None,
            }
            for s, e, n, d in rows
        ]
    }


ONE = show_json(
    1,
    "One",
    [
        {"season_number": 1, "air_date": "2026-09-01"},
        {"season_number": 2, "air_date": "2026-12-01"},
    ],
)
ONE_S1 = episodes((1, 1, "Pilot", "2026-09-01"), (1, 2, "Two", "2026-09-28"))
ONE_TV = {
    "network": {"name": "FX"},
    "_embedded": {
        "episodes": [
            {
                "season": 1,
                "number": 2,
                "name": "Two",
                "airstamp": "2026-09-29T01:00:00+00:00",
                "airtime": "21:00",
            }
        ]
    },
}
TWO = show_json(2, "Two", [{"season_number": 1, "air_date": "2026-01-01"}])


def world(sp_rows=None, tmdb_broken=(), tvmaze_broken=(), llm=None):
    sp = make_spreadsheet(
        **(sp_rows if sp_rows is not None else {"Tracked": [tracked(1, "One")]})
    )
    tmdb = FakeTmdb({1: ONE, 2: TWO}, {(1, 1): ONE_S1}, broken=tmdb_broken)
    tvmaze = FakeTvmaze(
        {"tt1": 11, "tt2": 22}, {11: ONE_TV, 22: {}}, broken=tvmaze_broken
    )
    return sp, Sheet(sp), tmdb, tvmaze, llm or FakeLlm()


def meta(sp):
    return {
        row[0]: (row[1] if len(row) > 1 else "")
        for row in sp.grid["Meta"][1:]
        if row and row[0]
    }


def test_first_run_writes_cards_tvmaze_id_schedule_and_meta():
    sp, sheet, tmdb, tvmaze, llm = world()
    report = run_daily(sheet, tmdb, tvmaze, llm, lambda url: None, NOW)
    assert report.ok
    cards = {r["card_id"]: r for r in sheet.read_all()["Cards"]}
    assert set(cards) == {"ep:1:S01E02", "season:1:2:2026-12-01"}
    assert (
        cards["ep:1:S01E02"]["link"]
        == "https://www.imdb.com/title/tt1/episodes/?season=1"
    )
    assert cards["ep:1:S01E02"]["status"] == "new"
    assert get_cell(sp, "Tracked", 1, "tvmaze_id") == "11"
    assert get_cell(sp, "Tracked", 1, "imdb_id") == "tt1"
    schedule = sheet.read_all()["Schedule"]
    assert [(r["airstamp"], r["network"]) for r in schedule] == [
        ("2026-09-28T21:00-04:00", "FX")
    ]
    assert schedule[0]["link"] == "https://www.imdb.com/title/tt1/episodes/?season=1"
    assert meta(sp) == {
        "last_run_at": "2026-09-28T06:00:00-04:00",
        "last_run_ok": "TRUE",
        "schedule_from": "2026-09-26",
        "failed_shows": "",
        "failed_steps": "",
    }
    assert llm.calls == ["suggestions", "news"]


def test_second_run_is_idempotent():
    _sp, sheet, tmdb, tvmaze, llm = world()
    run_daily(sheet, tmdb, tvmaze, llm, lambda url: None, NOW)
    report = run_daily(sheet, tmdb, tvmaze, llm, lambda url: None, NOW)
    assert (report.appended, report.updated) == (0, 0)
    assert len(sheet.read_all()["Cards"]) == 2


def test_noted_click_between_read_and_write_survives_content_update():
    sp, sheet, tmdb, tvmaze, llm = world()
    run_daily(sheet, tmdb, tvmaze, llm, lambda url: None, NOW)
    tmdb.seasons[(1, 1)] = episodes((1, 2, "Second", "2026-09-28"))
    real_write = sheet.write

    def racing_write(updates, appends):
        set_cell(sp, "Cards", "ep:1:S01E02", "status", "noted")
        real_write(updates, appends)

    sheet.write = racing_write
    run_daily(sheet, tmdb, tvmaze, llm, lambda url: None, NOW)
    assert get_cell(sp, "Cards", "ep:1:S01E02", "status") == "noted"
    assert get_cell(sp, "Cards", "ep:1:S01E02", "headline") == "S01E02 · Second"


def test_partial_failure_carries_schedule_and_reports():
    rows = {
        "Tracked": [tracked(1, "One"), tracked(2, "Two", tvmaze_id=22)],
        "Schedule": [
            {
                "tmdb_id": 2,
                "airstamp": "2026-09-30",
                "show_name": "Two",
                "episode_label": "S01E05",
            }
        ],
    }
    sp, sheet, tmdb, tvmaze, llm = world(rows, tvmaze_broken={22})
    report = run_daily(sheet, tmdb, tvmaze, llm, lambda url: None, NOW)
    assert not report.ok
    assert report.failed_shows == ["Two"]
    assert [(r["tmdb_id"], r["airstamp"]) for r in sheet.read_all()["Schedule"]] == [
        ("1", "2026-09-28T21:00-04:00"),
        ("2", "2026-09-30"),
    ]
    assert meta(sp)["last_run_ok"] == "FALSE"
    assert meta(sp)["failed_shows"] == "Two"
    assert "ep:1:S01E02" in {r["card_id"] for r in sheet.read_all()["Cards"]}


def test_llm_outage_still_writes_fact_cards():
    sp, sheet, tmdb, tvmaze, _ = world(llm=FakeLlm(fail=True))
    report = run_daily(sheet, tmdb, tvmaze, FakeLlm(fail=True), lambda url: None, NOW)
    assert report.failed_steps == ["suggestions", "news"]
    assert len(sheet.read_all()["Cards"]) == 2
    assert meta(sp)["failed_steps"] == "suggestions, news"


def test_duplicate_news_in_one_run_appended_once():
    url = "https://deadline.com/one-renewed"
    item = {
        "tmdb_id": 1,
        "headline": "One renewed",
        "summary": "s",
        "source_url": url,
        "published_date": "2026-09-27",
    }
    llm = FakeLlm(
        {"news": {"news": [item, item | {"headline": "Same story"}]}}, sources=[url]
    )
    _sp, sheet, tmdb, tvmaze, _ = world(llm=llm)
    run_daily(sheet, tmdb, tvmaze, llm, lambda u: "<html></html>", NOW)
    news = [r for r in sheet.read_all()["Cards"] if r["type"] == "news"]
    assert [(r["headline"], r["show_name"], r["image_url"]) for r in news] == [
        ("One renewed", "One", "https://image.tmdb.org/t/p/w342/p1.jpg")
    ]


def test_news_already_in_sheet_is_not_appended_again():
    url = "https://deadline.com/one-renewed"
    item = {
        "tmdb_id": 1,
        "headline": "One renewed",
        "summary": "s",
        "source_url": url,
        "published_date": "2026-09-27",
    }
    llm = FakeLlm({"news": {"news": [item]}}, sources=[url])
    _sp, sheet, tmdb, tvmaze, _ = world(llm=llm)
    run_daily(sheet, tmdb, tvmaze, llm, lambda u: "<html></html>", NOW)
    report = run_daily(sheet, tmdb, tvmaze, llm, lambda u: "<html></html>", NOW)
    assert report.appended == 0
    assert len([r for r in sheet.read_all()["Cards"] if r["type"] == "news"]) == 1


def test_empty_sheet_skips_llm_and_writes_meta():
    sp, sheet, tmdb, tvmaze, llm = world({})
    report = run_daily(sheet, tmdb, tvmaze, llm, lambda url: None, NOW)
    assert report.ok
    assert llm.calls == []
    assert meta(sp)["last_run_ok"] == "TRUE"
    assert sheet.read_all()["Schedule"] == []


def test_tmdb_failure_marks_show_failed_and_skips_it():
    _sp, sheet, tmdb, tvmaze, llm = world(tmdb_broken={1})
    report = run_daily(sheet, tmdb, tvmaze, llm, lambda url: None, NOW)
    assert report.failed_shows == ["One"]
    assert sheet.read_all()["Cards"] == []


def test_failure_logs_never_name_shows(capsys):
    _sp, sheet, tmdb, tvmaze, llm = world(tmdb_broken={1})
    run_daily(sheet, tmdb, tvmaze, llm, lambda url: None, NOW)
    output = capsys.readouterr()
    assert "One" not in output.out + output.err
    assert "FAILED" in output.out


def test_http_failure_logs_leak_no_urls_or_ids(capsys):
    import httpx

    request = httpx.Request(
        "GET", "https://api.themoviedb.org/3/tv/1434?append_to_response=external_ids"
    )
    error = httpx.HTTPStatusError(
        "Client error '404 Not Found' for url '…/tv/1434'",
        request=request,
        response=httpx.Response(404, request=request),
    )
    _sp, sheet, tmdb, tvmaze, llm = world()
    tmdb.show = lambda *a, **k: (_ for _ in ()).throw(error)
    run_daily(sheet, tmdb, tvmaze, llm, lambda url: None, NOW)
    out = capsys.readouterr()
    logged = out.out + out.err
    assert "1434" not in logged and "themoviedb" not in logged
    assert "HTTPStatusError 404" in logged


def test_postponed_or_undated_episode_corrects_existing_card_and_hides_it():
    sp, sheet, tmdb, tvmaze, llm = world()
    run_daily(sheet, tmdb, tvmaze, llm, lambda url: None, NOW)
    tmdb.seasons[(1, 1)] = episodes(
        (1, 1, "Pilot", "2026-09-01"), (1, 2, "Two (delayed)", "2026-09-30")
    )
    run_daily(sheet, tmdb, tvmaze, llm, lambda url: None, NOW)
    assert get_cell(sp, "Cards", "ep:1:S01E02", "date") == "2026-09-30"
    assert get_cell(sp, "Cards", "ep:1:S01E02", "headline") == "S01E02 · Two (delayed)"
    assert get_cell(sp, "Cards", "ep:1:S01E02", "current") == "FALSE"
    assert get_cell(sp, "Cards", "ep:1:S01E02", "status") == "new"

    run_daily(
        sheet,
        tmdb,
        tvmaze,
        llm,
        lambda url: None,
        datetime(2026, 9, 30, 6, 0, tzinfo=TZ),
    )
    assert get_cell(sp, "Cards", "ep:1:S01E02", "current") == "TRUE"

    tmdb.seasons[(1, 1)] = episodes((1, 1, "Pilot", "2026-09-01"), (1, 2, "Two", None))
    run_daily(sheet, tmdb, tvmaze, llm, lambda url: None, NOW)
    assert get_cell(sp, "Cards", "ep:1:S01E02", "date") == ""
    assert get_cell(sp, "Cards", "ep:1:S01E02", "current") == "FALSE"


def test_schedule_links_match_tmdb_episodes_by_air_date_not_number():
    _sp, sheet, tmdb, tvmaze, llm = world()
    renumbered = {
        "network": {"name": "Hulu"},
        "_embedded": {
            "episodes": [
                {
                    "season": 14,
                    "number": 2,
                    "name": "Two",
                    "airstamp": "2026-09-29T01:00:00+00:00",
                    "airtime": "21:00",
                    "airdate": "2026-09-28",
                },
            ]
        },
    }
    tvmaze.shows[11] = renumbered
    looked_up = []

    def episode_imdb(tmdb_id, season, episode):
        looked_up.append((season, episode))
        return "tt777" if (season, episode) == (1, 2) else None

    tmdb.episode_imdb = episode_imdb
    run_daily(sheet, tmdb, tvmaze, llm, lambda url: None, NOW)
    assert (
        sheet.read_all()["Schedule"][0]["link"] == "https://www.imdb.com/title/tt777/"
    )
    assert (14, 2) not in looked_up


class FakeOmdb:
    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def episode_imdb(self, show_imdb, season, airdate, number):
        self.calls.append((show_imdb, season, airdate, number))
        return self.answers.get((show_imdb, season, airdate, number))


def test_schedule_link_falls_back_to_omdb_when_tmdb_has_no_imdb_id():
    _sp, sheet, tmdb, tvmaze, llm = world()
    omdb = FakeOmdb({("tt1", 1, "2026-09-28", 2): "tt555"})
    run_daily(sheet, tmdb, tvmaze, llm, lambda url: None, NOW, omdb=omdb)
    assert (
        sheet.read_all()["Schedule"][0]["link"] == "https://www.imdb.com/title/tt555/"
    )


def test_omdb_miss_keeps_the_season_list_link():
    _sp, sheet, tmdb, tvmaze, llm = world()
    run_daily(sheet, tmdb, tvmaze, llm, lambda url: None, NOW, omdb=FakeOmdb({}))
    assert (
        sheet.read_all()["Schedule"][0]["link"]
        == "https://www.imdb.com/title/tt1/episodes/?season=1"
    )


def test_ran_today_only_counts_a_successful_run_on_the_same_toronto_day():
    from datetime import date

    from job.daily import ran_today

    today = date(2026, 9, 29)

    def meta(**values):
        return [{"key": k, "value": v} for k, v in values.items()]

    assert ran_today(
        meta(last_run_at="2026-09-29T06:17:40-04:00", last_run_ok="True"), today
    )
    assert ran_today(
        meta(last_run_at="2026-09-29T10:17:40+00:00", last_run_ok="True"), today
    )
    assert not ran_today(
        meta(last_run_at="2026-09-29T06:17:40-04:00", last_run_ok="False"), today
    )
    assert not ran_today(
        meta(last_run_at="2026-09-28T23:30:00-04:00", last_run_ok="True"), today
    )
    assert not ran_today(
        meta(last_run_at="2026-09-29T03:30:00+00:00", last_run_ok="True"), today
    )
    assert not ran_today([], today)
    assert not ran_today(meta(last_run_at="garbage", last_run_ok="True"), today)


def test_failure_log_includes_the_api_error_code(capsys):
    class RateLimitError(Exception):
        code = "credit_balance_exhausted"
        status_code = 429

    class Broke:
        def __init__(self):
            self.responses = NS(create=self.create)

        def create(self, **kwargs):
            raise RateLimitError("You have no credits remaining.")

    _sp, sheet, tmdb, tvmaze, _ = world()
    run_daily(sheet, tmdb, tvmaze, Broke(), lambda url: None, NOW)
    logged = capsys.readouterr().out
    assert "FAILED suggestions: RateLimitError 429 credit_balance_exhausted" in logged
    assert "no credits remaining" not in logged


def test_research_off_without_an_llm_client_is_not_a_failure():
    sp, sheet, tmdb, tvmaze, _ = world()
    report = run_daily(sheet, tmdb, tvmaze, None, lambda url: None, NOW)
    assert report.ok and report.failed_steps == []
    assert {r["card_id"] for r in sheet.read_all()["Cards"]} == {
        "ep:1:S01E02",
        "season:1:2:2026-12-01",
    }
    assert meta(sp)["last_run_ok"] == "TRUE"
