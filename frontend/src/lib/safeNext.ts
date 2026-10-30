const LOGIN_PAGES = ['/login', '/signup']

/** Where to go after logging in: a path on this site, or home, so a crafted link cannot send anyone elsewhere. */
export function safeNext(raw: string | null): string {
  if (!raw || !raw.startsWith('/')) return '/'
  try {
    const url = new URL(raw, window.location.origin)
    if (url.origin !== window.location.origin || LOGIN_PAGES.includes(url.pathname)) return '/'
    return url.pathname + url.search + url.hash
  } catch {
    return '/'
  }
}

/** The login page for a request the server refused, coming back here afterwards. */
export function goToLogin() {
  const { pathname, search, hash } = window.location
  window.location.assign(`/login?next=${encodeURIComponent(pathname + search + hash)}`)
}
