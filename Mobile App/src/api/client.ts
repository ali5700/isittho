import { API_BASE_URL } from "../config";
import type { ApiErrorPayload, CheckResponse, SubmitResponse } from "./types";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError(
      `Couldn't reach the server at ${API_BASE_URL}. Check that the backend is running and reachable.`,
      0
    );
  }

  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const payload = (await response.json()) as ApiErrorPayload;
      if (payload?.detail) detail = payload.detail;
    } catch {
      // response body wasn't JSON; fall back to the generic message above
    }
    throw new ApiError(detail, response.status);
  }

  return (await response.json()) as T;
}

export function checkSituation(text: string): Promise<CheckResponse> {
  return postJson<CheckResponse>("/check", { text });
}

export function submitSituation(text: string): Promise<SubmitResponse> {
  return postJson<SubmitResponse>("/submit", { text });
}
