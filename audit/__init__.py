"""Dependency-free website audit engine.

Pure standard library on purpose: the rule logic must not depend on a web framework, an ORM,
or a headless browser, so it can run as a CLI, inside the FastAPI service, or in CI.

See services/api/app/modules/ for the service-layer wrappers.
"""

__version__ = "0.1.0"
