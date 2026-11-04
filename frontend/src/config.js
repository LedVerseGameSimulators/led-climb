/** Climb stack ports — must match api/config.py and ws_bridge.py defaults. */
export const API_PORT = 8002
export const WS_BRIDGE_PORT = 8766
export const API_URL = `http://localhost:${API_PORT}`
export const WS_BRIDGE_URL = `http://localhost:${WS_BRIDGE_PORT}`
/** Central RFID server — validates card sessions (Machine 5). */
/** Runtime value injected by the packaged API (per-PC) wins over the build-time env. */
export const RFID_API_URL =
  (typeof window !== 'undefined' && window.__ACTIVERSE__?.rfidApiUrl) ||
  import.meta.env.VITE_RFID_API_URL ||
  'http://localhost:9000'
