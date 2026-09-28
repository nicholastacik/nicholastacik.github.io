const KEY = "tv-tracker-token";

export class Auth {
  constructor({ clientId, scope, storage, now = () => Date.now() }) {
    this.clientId = clientId;
    this.scope = scope;
    this.storage = storage;
    this.now = now;
    this.token = null;
    this.expiresAt = 0;
    try {
      const saved = JSON.parse(this.storage.getItem(KEY));
      if (saved && saved.expiresAt > this.now()) {
        this.token = saved.token;
        this.expiresAt = saved.expiresAt;
      }
    } catch {
      // no storage or bad data: start signed out
    }
  }

  valid() {
    return Boolean(this.token) && this.expiresAt - 60_000 > this.now();
  }

  expire() {
    this.token = null;
    this.expiresAt = 0;
    try {
      this.storage.removeItem(KEY);
    } catch {
      // nothing saved
    }
  }

  connect(prompt = "") {
    return new Promise((resolve, reject) => {
      const client = globalThis.google.accounts.oauth2.initTokenClient({
        client_id: this.clientId,
        scope: this.scope,
        callback: (response) => {
          if (response.error) {
            reject(new Error(response.error));
            return;
          }
          this.token = response.access_token;
          this.expiresAt = this.now() + Number(response.expires_in) * 1000;
          try {
            this.storage.setItem(KEY, JSON.stringify({ token: this.token, expiresAt: this.expiresAt }));
          } catch {
            // token still works for this page
          }
          resolve();
        },
        error_callback: (error) => reject(new Error(error?.type ?? "popup_closed")),
      });
      client.requestAccessToken({ prompt });
    });
  }
}
