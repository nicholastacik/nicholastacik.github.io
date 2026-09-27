import json
from datetime import date
from types import SimpleNamespace as NS

from job import llm

SEVERANCE = {"tmdb_id": 95396, "name": "Severance", "first_air_year": 2022}
BEAR = {"tmdb_id": 136315, "name": "The Bear", "first_air_year": 2022}


def test_suggestions_prompt_fills_every_placeholder():
    prompt = llm.suggestions_prompt([SEVERANCE], [BEAR], [], 2)
    assert "- Severance (2022)" in prompt
    assert "- The Bear (2022)" in prompt
    assert "(none)" in prompt
    assert "Suggest 2 show(s)" in prompt
    assert "$" not in prompt


def test_news_prompt_includes_ids_and_recent_headlines():
    recent = [{"show": "Severance", "headline": "Severance renewed for season 3"}]
    prompt = llm.news_prompt([SEVERANCE], recent, date(2026, 9, 27), 7)
    assert "Today is 2026-09-27" in prompt
    assert "last 7 days" in prompt
    assert "- Severance (2022) [tmdb_id 95396]" in prompt
    assert "- Severance: Severance renewed for season 3" in prompt
    assert "$" not in prompt


def test_schemas_have_object_roots_and_are_strict():
    for schema, key in [(llm.SUGGESTIONS_SCHEMA, "suggestions"), (llm.NEWS_SCHEMA, "news")]:
        assert schema["type"] == "object"
        assert schema["required"] == [key]
        assert schema["additionalProperties"] is False
        item = schema["properties"][key]["items"]
        assert item["additionalProperties"] is False
        assert sorted(item["required"]) == sorted(item["properties"])


def fake_response(payload):
    return NS(
        output=[
            NS(
                type="web_search_call",
                action=NS(type="search", sources=[NS(url="https://deadline.com/a/"), NS(url="https://variety.com/b")]),
            ),
            NS(type="web_search_call", action=NS(type="open_page", url="https://deadline.com/a/")),
            NS(
                type="message",
                content=[
                    NS(
                        type="output_text",
                        annotations=[NS(type="url_citation", url="https://tvline.com/c?utm_source=chatgpt.com")],
                    )
                ],
            ),
        ],
        output_text=json.dumps(payload),
        usage=NS(input_tokens=1200, output_tokens=300),
    )


def test_extract_sources_collects_search_sources_and_citations():
    urls, searches = llm.extract_sources(fake_response({}))
    assert urls == {"https://deadline.com/a/", "https://variety.com/b", "https://tvline.com/c?utm_source=chatgpt.com"}
    assert searches == 1


def test_extract_sources_tolerates_missing_action_and_sources():
    response = NS(output=[NS(type="web_search_call"), NS(type="web_search_call", action=NS(type="search", sources=None))])
    assert llm.extract_sources(response) == (set(), 1)


def test_run_sends_web_search_and_strict_schema():
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return fake_response({"news": []})

    client = NS(responses=NS(create=create))
    result = llm.run(client, "PROMPT", "news", llm.NEWS_SCHEMA, model="m", effort="low")

    sent = calls[0]
    assert sent["model"] == "m"
    assert sent["input"] == "PROMPT"
    assert sent["tools"] == [{"type": "web_search"}]
    assert sent["include"] == ["web_search_call.action.sources"]
    assert sent["reasoning"] == {"effort": "low"}
    assert sent["text"]["format"] == {"type": "json_schema", "name": "news", "strict": True, "schema": llm.NEWS_SCHEMA}
    assert result.data == {"news": []}
    assert (result.input_tokens, result.output_tokens, result.searches) == (1200, 300, 1)
    assert "https://variety.com/b" in result.sources
