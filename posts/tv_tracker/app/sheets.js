import { HEADERS } from "./headers.js";
import { rowsFromValues } from "./state.js";

const BASE = "https://sheets.googleapis.com/v4/spreadsheets";

export class AuthError extends Error {}
export class ForbiddenError extends Error {}
export class SheetsError extends Error {
  constructor(status, body) {
    super(`Sheets API ${status}`);
    this.status = status;
    this.body = body;
  }
}

export function tabRange(tab) {
  return `${tab}!A:${String.fromCharCode(64 + HEADERS[tab].length)}`;
}

export class SheetsClient {
  constructor({ sheetId, getToken, fetchFn = (...args) => fetch(...args) }) {
    this.sheetId = sheetId;
    this.getToken = getToken;
    this.fetchFn = fetchFn;
    this.ids = null;
  }

  async call(path, init = {}) {
    const response = await this.fetchFn(`${BASE}/${this.sheetId}${path}`, {
      ...init,
      headers: { Authorization: `Bearer ${this.getToken()}`, "Content-Type": "application/json" },
    });
    if (response.status === 401) throw new AuthError("Google session expired");
    if (response.status === 403) throw new ForbiddenError("No access to this Sheet");
    if (!response.ok) throw new SheetsError(response.status, await response.text());
    return response.json();
  }

  async get(ranges) {
    const params = new URLSearchParams({ valueRenderOption: "UNFORMATTED_VALUE" });
    for (const range of ranges) params.append("ranges", range);
    const data = await this.call(`/values:batchGet?${params}`);
    return data.valueRanges.map((valueRange) => valueRange.values ?? []);
  }

  async readAll() {
    const tabs = Object.keys(HEADERS);
    const values = await this.get(tabs.map(tabRange));
    return Object.fromEntries(tabs.map((tab, i) => [tab, rowsFromValues(tab, values[i])]));
  }

  async sheetIds() {
    if (!this.ids) {
      const data = await this.call("?fields=sheets.properties(sheetId,title)");
      this.ids = Object.fromEntries(data.sheets.map((sheet) => [sheet.properties.title, sheet.properties.sheetId]));
    }
    return this.ids;
  }

  async batchUpdate(requests) {
    return this.call(":batchUpdate", { method: "POST", body: JSON.stringify({ requests }) });
  }
}
