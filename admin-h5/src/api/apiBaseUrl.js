// Single authority for resolving the backend API origin (Phase F1G-CM-RF).
// Both the merchant/staff request client (request.js) and the SuperAdmin
// request client (superRequest.js) must resolve the SAME origin the SAME
// way -- a second, independently-drifting copy of this logic is exactly
// what let SuperAdmin's raw-axios calls silently target the wrong origin
// locally (and left production routing unproven from source alone).
export function resolveApiBaseURL() {
  const envBaseURL = import.meta.env.VITE_API_BASE_URL
  const hostname = window.location.hostname

  if (hostname === 'saas.zhangbaiyang.com') {
    return '/api'
  }

  return envBaseURL || '/api'
}
