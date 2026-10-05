export function searchUrl(query, apiKey) {
  return `https://api.themoviedb.org/3/search/tv?${new URLSearchParams({ query, api_key: apiKey })}`;
}

export function mapResults(results) {
  return results.map((result) => ({
    tmdb_id: result.id,
    name: result.name,
    original_name: result.original_name && result.original_name !== result.name ? result.original_name : "",
    first_air_year: Number(String(result.first_air_date ?? "").slice(0, 4)) || "",
    poster_url: result.poster_path ? `https://image.tmdb.org/t/p/w342${result.poster_path}` : "",
    country: (result.origin_country ?? [])[0] ?? "",
  }));
}

export async function searchShows(query, apiKey, fetchFn = (...args) => fetch(...args)) {
  const response = await fetchFn(searchUrl(query, apiKey));
  if (!response.ok) throw new Error(`TMDB ${response.status}`);
  return mapResults((await response.json()).results).slice(0, 10);
}

export async function fillMissingPosters(cards, apiKey, fetchFn = (...args) => fetch(...args)) {
  const missing = cards.filter((card) => card.type === "suggestion" && !card.image_url && Number(card.tmdb_id));
  await Promise.all(
    missing.map(async (card) => {
      try {
        const response = await fetchFn(`https://api.themoviedb.org/3/tv/${Number(card.tmdb_id)}?${new URLSearchParams({ api_key: apiKey })}`);
        if (!response.ok) return;
        const { poster_path } = await response.json();
        if (poster_path) card.image_url = `https://image.tmdb.org/t/p/w342${poster_path}`;
      } catch {}
    }),
  );
  return missing.length;
}

export function resultLabel(show) {
  const details = [show.first_air_year, show.country].filter(Boolean).join(", ");
  return details ? `${show.name} (${details})` : show.name;
}
