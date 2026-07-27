"""Shared enumerations used across models, schemas, and audit modules."""

from enum import StrEnum


class ScanStatus(StrEnum):
    QUEUED = "queued"
    CRAWLING = "crawling"
    AUDITING = "auditing"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ModuleKey(StrEnum):
    """One entry per audit module in PRD §5."""

    CRAWL = "crawl"
    IMAGES = "images"
    SEO = "seo"
    PERFORMANCE = "performance"
    ACCESSIBILITY = "accessibility"
    DESIGN = "design"
    CONTENT = "content"
    BUGS = "bugs"
    RESPONSIVE = "responsive"
    SCREENSHOTS = "screenshots"
    FORMS = "forms"
    CHECKLIST = "checklist"


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Priority(StrEnum):
    P0 = "p0"
    P1 = "p1"
    P2 = "p2"
    P3 = "p3"


class ReportFormat(StrEnum):
    """Export targets from PRD §14 (Module 14)."""

    PDF = "pdf"
    XLSX = "xlsx"
    CSV = "csv"
    MARKDOWN = "markdown"
    DOCX = "docx"
    HTML = "html"


class Role(StrEnum):
    """PRD §19."""

    ADMIN = "admin"
    QA = "qa"
    DEVELOPER = "developer"
    DESIGNER = "designer"
    SEO = "seo"
    MANAGER = "manager"
    CLIENT = "client"


# PRD §9 (Module 9) — viewport widths exercised by responsive testing.
RESPONSIVE_BREAKPOINTS: tuple[int, ...] = (
    320,
    360,
    375,
    390,
    414,
    768,
    820,
    1024,
    1280,
    1440,
    1920,
)
