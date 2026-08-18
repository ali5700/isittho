import { Platform } from "react-native";

// Override at build/run time with, e.g.:
//   EXPO_PUBLIC_API_URL=http://192.168.1.23:8000 npx expo start
// This is required when running on a physical device, since "localhost"
// there refers to the device itself, not your dev machine.
const envUrl = process.env.EXPO_PUBLIC_API_URL;

function defaultApiUrl(): string {
  if (Platform.OS === "android") {
    // 10.0.2.2 is the Android emulator's alias for the host machine's localhost.
    return "http://10.0.2.2:8000";
  }
  return "http://localhost:8000";
}

export const API_BASE_URL = envUrl && envUrl.length > 0 ? envUrl : defaultApiUrl();
