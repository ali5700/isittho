// Production backend, reachable over the internet (not just local WiFi).
// Override at build/run time for local development, e.g.:
//   EXPO_PUBLIC_API_URL=http://10.0.2.2:8000 npx expo start        (Android emulator)
//   EXPO_PUBLIC_API_URL=http://192.168.1.23:8000 npx expo start    (physical device on same WiFi)
const PRODUCTION_API_URL = "https://isittho-production.up.railway.app";

const envUrl = process.env.EXPO_PUBLIC_API_URL;

export const API_BASE_URL = envUrl && envUrl.length > 0 ? envUrl : PRODUCTION_API_URL;
