// Mirrors the Pydantic models in the isittho FastAPI backend (main.py).

export interface SimilarSubmission {
  text_preview: string;
  category: string;
  outcome_label: string;
  similarity: number;
}

export interface CheckResponse {
  query: string;
  similar_submissions: SimilarSubmission[];
  verdict_breakdown: Record<string, number>;
  top_label: string;
  needs_support_resources: boolean;
}

export interface ApiErrorPayload {
  detail: string;
}
