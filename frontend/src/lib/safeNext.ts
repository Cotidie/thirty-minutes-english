/** Where to go after logging in: a path on this site, or home, so a crafted link cannot send anyone elsewhere. */
export function safeNext(raw: string | null): string {
  if (!raw || !raw.startsWith('/')) return '/'
  const url = new URL(raw, window.location.origin)
  return url.origin === window.location.origin ? url.pathname + url.search + url.hash : '/'
}

/** The login page for a request the server refused, coming back here afterwards. */
export function goToLogin() {
  const { pathname, search, hash } = window.location
  window.location.assign(`/login?next=${encodeURIComponent(pathname + search + hash)}`)
}
