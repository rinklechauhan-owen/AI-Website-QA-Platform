import type {
  CreateScanInput,
  Finding,
  ModuleKey,
  Scan,
  ScanDetail,
  Severity,
} from "@/lib/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const API_PREFIX = "/api/v1";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${API_PREFIX}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });

  if (!response.ok) {
    // FastAPI returns { detail: string } for HTTPException.
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new ApiError(response.status, body?.detail ?? response.statusText);
  }

  return response.json() as Promise<T>;
}

export function createScan(input: CreateScanInput): Promise<Scan> {
  return request<Scan>("/scans", { method: "POST", body: JSON.stringify(input) });
}

export function listScans(params: { limit?: number; offset?: number } = {}): Promise<Scan[]> {
  const query = new URLSearchParams();
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.offset !== undefined) query.set("offset", String(params.offset));

  const suffix = query.size > 0 ? `?${query}` : "";
  return request<Scan[]>(`/scans${suffix}`);
}

export function getScan(scanId: string): Promise<ScanDetail> {
  return request<ScanDetail>(`/scans/${scanId}`);
}

export function listFindings(
  scanId: string,
  filters: { module?: ModuleKey; severity?: Severity } = {},
): Promise<Finding[]> {
  const query = new URLSearchParams();
  if (filters.module) query.set("module", filters.module);
  if (filters.severity) query.set("severity", filters.severity);

  const suffix = query.size > 0 ? `?${query}` : "";
  return request<Finding[]>(`/scans/${scanId}/findings${suffix}`);
}

export function cancelScan(scanId: string): Promise<Scan> {
  return request<Scan>(`/scans/${scanId}/cancel`, { method: "POST" });
}
