// In-memory only. SuperAdmin.vue also keeps `let superToken = ''` because a
// route change can remount the page. This is not localStorage: a refresh
// still drops the session, same as before.
let sessionToken = ''

export function setSuperSessionToken(value) {
  sessionToken = value || ''
}

export function getSuperSessionToken() {
  return sessionToken
}
