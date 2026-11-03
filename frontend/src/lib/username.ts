/** The server's rule for the name others know an account by (`backend/app/accounts/usernames.py`), checked here first
 * so a blank can say what is wrong while it is filled. The server checks again and has the last word. */
const USERNAME = /^[0-9A-Za-z_가-힣]{2,20}$/

export const USERNAME_HINT = '2 to 20 letters, digits or _. Korean is fine.'

/** The name as the server keeps it: composed, since a Mac types Korean decomposed, and trimmed. */
export function cleanUsername(typed: string): string {
  return typed.normalize('NFC').trim()
}

export function isUsername(typed: string): boolean {
  return USERNAME.test(cleanUsername(typed))
}
