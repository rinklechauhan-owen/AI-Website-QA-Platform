// Mirrors services/api/app/enums.py and app/schemas — keep the two in sync.

export const MODULE_KEYS = [
  "crawl",
  "images",
  "seo",
  "performance",
  "accessibility",
  "design",
  "content",
  "bugs",
  "responsive",
  "screenshots",
  "forms",
  "checklist",
] as const;

export type ModuleKey = (typeof MODULE_KEYS)[number];

export const MODULE_LABELS: Record<ModuleKey, string> = {
  crawl: "Website Crawl",
  images: "Image Audit",
  seo: "SEO Audit",
  performance: "Performance",
  accessibility: "Accessibility",
  design: "Design Review",
  content: "Content Review",
  bugs: "Bug Detection",
  responsive: "Responsive Testing",
  screenshots: "Screenshot Analysis",
  forms: "Forms Testing",
  checklist: "QA Checklist",
};

export type ScanStatus =
  | "queued"
  | "crawling"
  | "auditing"
  | "analyzing"
  | "completed"
  | "failed"
  | "cancelled";

export const TERMINAL_STATUSES: readonly ScanStatus[] = ["completed", "failed", "cancelled"];

export type Severity = "critical" | "high" | "medium" | "low" | "info";

export type Priority = "p0" | "p1" | "p2" | "p3";

export type ReportFormat = "pdf" | "xlsx" | "csv" | "markdown" | "docx" | "html";

export interface Scan {
  id: string;
  url: string;
  status: ScanStatus;
  requested_modules: string[];
  overall_score: number | null;
  scores: Record<string, number>;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface ScanSummary {
  total_findings: number;
  critical: number;
  high: number;
  medium: number;
  low: number;
  info: number;
  pages_crawled: number;
}

export interface ScanDetail extends Scan {
  summary: ScanSummary;
}

export interface Finding {
  id: string;
  page_id: string | null;
  module: ModuleKey;
  rule: string;
  severity: Severity;
  priority: Priority | null;
  title: string;
  detail: string | null;
  selector: string | null;
  snippet: string | null;
  recommendation: Record<string, unknown>;
  meta: Record<string, unknown>;
}

export interface CreateScanInput {
  url: string;
  modules?: ModuleKey[];
  max_pages?: number;
  max_depth?: number;
}
