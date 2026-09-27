import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from string import Template

from job import config

PROMPTS = Path(__file__).parent / "prompts"


def _array_schema(key: str, properties: dict) -> dict:
    return {
        "type": "object",
        "properties": {
            key: {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": properties,
                    "required": list(properties),
                    "additionalProperties": False,
                },
            }
        },
        "required": [key],
        "additionalProperties": False,
    }


SUGGESTIONS_SCHEMA = _array_schema(
    "suggestions",
    {"title": {"type": "string"}, "year": {"type": "integer"}, "reason": {"type": "string"}},
)
NEWS_SCHEMA = _array_schema(
    "news",
    {
        "tmdb_id": {"type": "integer"},
        "headline": {"type": "string"},
        "summary": {"type": "string"},
        "source_url": {"type": "string"},
        "published_date": {"type": "string"},
    },
)


@dataclass
class LlmResult:
    data: dict
    sources: set[str]
    input_tokens: int
    output_tokens: int
    searches: int


def _bullets(lines) -> str:
    return "\n".join(f"- {line}" for line in lines) or "(none)"


def _label(show: dict) -> str:
    return f"{show['name']} ({show['first_air_year']})"


def _template(name: str) -> Template:
    return Template((PROMPTS / f"{name}.md").read_text())


def suggestions_prompt(tracked: list[dict], ignored: list[dict], pending: list[dict], k: int) -> str:
    return _template("suggestions").substitute(
        tracked=_bullets(map(_label, tracked)),
        ignored=_bullets(map(_label, ignored)),
        pending=_bullets(map(_label, pending)),
        k=k,
    )


def news_prompt(tracked: list[dict], recent: list[dict], today: date, window_days: int) -> str:
    return _template("news").substitute(
        today=today.isoformat(),
        window=window_days,
        tracked=_bullets(f"{_label(s)} [tmdb_id {s['tmdb_id']}]" for s in tracked),
        recent=_bullets(f"{r['show']}: {r['headline']}" for r in recent),
    )


def extract_sources(response) -> tuple[set[str], int]:
    urls, searches = set(), 0
    for item in response.output:
        if item.type == "web_search_call":
            action = getattr(item, "action", None)
            if getattr(action, "type", None) == "search":
                searches += 1
                urls.update(source.url for source in getattr(action, "sources", None) or [])
        elif item.type == "message":
            for part in item.content:
                for annotation in getattr(part, "annotations", None) or []:
                    if annotation.type == "url_citation":
                        urls.add(annotation.url)
    return urls, searches


def run(
    client,
    prompt: str,
    name: str,
    schema: dict,
    model: str = config.OPENAI_MODEL,
    effort: str = config.OPENAI_REASONING_EFFORT,
) -> LlmResult:
    response = client.responses.create(
        model=model,
        reasoning={"effort": effort},
        tools=[{"type": "web_search"}],
        include=["web_search_call.action.sources"],
        input=prompt,
        text={"format": {"type": "json_schema", "name": name, "strict": True, "schema": schema}},
    )
    sources, searches = extract_sources(response)
    return LlmResult(
        data=json.loads(response.output_text),
        sources=sources,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        searches=searches,
    )
