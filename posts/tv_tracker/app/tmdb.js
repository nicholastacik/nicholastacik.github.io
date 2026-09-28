export function searchUrl(query, apiKey) {
  return `https://api.themoviedb.org/3/search/tv?${new URLSearchParams({ query, api_key: apiKey })}`;
}

export function mapResults(results) {
  return results.map((result) => ({
    tmdb_id: result.id,
    name: result.name,
    first_air_year: Number(String(result.first_air_date ?? "").slice(0, 4)) || "",
    poster_url: result.poster_path ? `https://image.tmdb.org/t/p/w342${result.poster_path}` : "",
  }));
}

export async function searchShows(query, apiKey, fetchFn = (...args) => fetch(...args)) {
  const response = await fetchFn(searchUrl(query, apiKey));
  if (!response.ok) throw new Error(`TMDB ${response.status}`);
  return mapResults((await response.json()).results).slice(0, 10);
}
