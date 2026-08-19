import axios from 'axios'
import { resolveApiBaseURL } from './apiBaseUrl'

// SuperAdmin's own request client (Phase F1G-CM-RF). Shares the exact same
// API-origin authority as the merchant/staff client (request.js) via
// resolveApiBaseURL() -- there is only ever one source of truth for "which
// backend origin", never a second relative-to-browser-origin fallback that
// silently drifts in local dev (that drift is what forced a temporary Vite
// proxy in CM-C/CM-D).
//
// Deliberately NOT the merchant `instance` from request.js: SuperAdmin auth
// is X-Super-Token, set explicitly per call by each api/super*.js function
// (same convention as before this fix) -- never the merchant Authorization
// header, and never the merchant client's on-401 redirect-to-/login, which
// would hijack the SuperAdmin session instead of just dropping back to the
// password screen. No response-unwrapping interceptor either: callers keep
// reading `res.data.code` off the raw AxiosResponse, exactly as before.
const superRequest = axios.create({
  baseURL: resolveApiBaseURL(),
  timeout: 10000,
})

export default superRequest
