"""Regenerate examples/sample-report.html from examples/sample-page.html.

Doubles as the shortest example of using the engine as a library rather than a CLI:

    python examples/generate_sample.py

Run it from the repository root.
"""

import sys
from pathlib import Path

# Allow running as a plain script from the repo root without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audit.engine import audit_response
from audit.fetch import Response
from audit.report import html as html_report
from audit.report import terminal as terminal_report

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "sample-page.html"
TARGET = HERE / "sample-report.html"

# The fixture stands in for this URL so relative paths resolve the way they would live.
SAMPLE_URL = "https://northgate-studio.test/"


def main() -> int:
    markup = SOURCE.read_text(encoding="utf-8")

    # Audit an in-memory response rather than fetching, so the sample is reproducible.
    response = Response(
        url=SAMPLE_URL,
        status=200,
        body=markup,
        headers={"content-type": "text/html; charset=utf-8"},
        elapsed_ms=142,
        byte_size=len(markup.encode("utf-8")),
    )

    result = audit_response(response, SAMPLE_URL)

    TARGET.write_text(html_report.render(result), encoding="utf-8")

    print(terminal_report.render(result, color=False))
    print(f"\nWrote {TARGET}")
    print(f"Overall {result.overall_score}/100 · {sum(result.counts.values())} findings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
