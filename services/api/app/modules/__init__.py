"""Audit module registry — maps a ModuleKey to its implementation."""

from app.enums import ModuleKey
from app.modules.accessibility import AccessibilityModule
from app.modules.base import AuditModule
from app.modules.bugs import BugsModule
from app.modules.checklist import ChecklistModule
from app.modules.content import ContentModule
from app.modules.crawl import CrawlModule
from app.modules.design import DesignModule
from app.modules.forms import FormsModule
from app.modules.images import ImagesModule
from app.modules.performance import PerformanceModule
from app.modules.responsive import ResponsiveModule
from app.modules.screenshots import ScreenshotsModule
from app.modules.seo import SeoModule

REGISTRY: dict[ModuleKey, type[AuditModule]] = {
    ModuleKey.CRAWL: CrawlModule,
    ModuleKey.IMAGES: ImagesModule,
    ModuleKey.SEO: SeoModule,
    ModuleKey.PERFORMANCE: PerformanceModule,
    ModuleKey.ACCESSIBILITY: AccessibilityModule,
    ModuleKey.DESIGN: DesignModule,
    ModuleKey.CONTENT: ContentModule,
    ModuleKey.BUGS: BugsModule,
    ModuleKey.RESPONSIVE: ResponsiveModule,
    ModuleKey.SCREENSHOTS: ScreenshotsModule,
    ModuleKey.FORMS: FormsModule,
    ModuleKey.CHECKLIST: ChecklistModule,
}


def get_module(key: ModuleKey) -> AuditModule:
    """Instantiate the module registered for ``key``."""
    try:
        return REGISTRY[key]()
    except KeyError:
        raise ValueError(f"No audit module registered for '{key}'") from None


__all__ = ["REGISTRY", "AuditModule", "get_module"]
