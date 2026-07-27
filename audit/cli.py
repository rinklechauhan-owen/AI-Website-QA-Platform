"""Command line entry point: python -m audit <url>"""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path
from typing import List, Optional

from audit import __version__
from audit.engine import audit_url
from audit.fetch import DEFAULT_TIMEOUT, DEFAULT_USER_AGENT, FetchError
from audit.findings import Severity
from audit.report import html as html_report
from audit.report import terminal as terminal_report

# Exit codes: 0 clean, 1 findings at or above --fail-on, 2 could not audit.
EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_ERROR = 2

_FAIL_ON_CHOICES = [severity.value for severity in Severity]

_SEVERITY_RANK = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFO: 4,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m audit",
        description="Audit a web page for SEO, image accessibility, and link problems. "
        "Uses only the Python standard library — no third-party packages required.",
        epilog="Examples:\n"
        "  python -m audit example.com\n"
        "  python -m audit https://example.com --format html --out report.html --open\n"
        "  python -m audit https://example.com --check-links --format json\n"
        "  python -m audit https://example.com --fail-on high   # for CI\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("url", help="page to audit; the https:// scheme is added if omitted")
    parser.add_argument(
        "-f",
        "--format",
        choices=("text", "html", "json"),
        default="text",
        help="output format (default: text)",
    )
    parser.add_argument(
        "-o", "--out", metavar="FILE", help="write the report to FILE instead of stdout"
    )
    parser.add_argument(
        "--open",
        action="store_true",
        dest="open_after",
        help="open the written report in your browser (implies --format html)",
    )
    parser.add_argument(
        "--check-links",
        action="store_true",
        help="also verify every link resolves (makes extra HTTP requests)",
    )
    parser.add_argument(
        "--max-links",
        type=int,
        default=40,
        metavar="N",
        help="cap on links checked by --check-links (default: 40)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        metavar="SECONDS",
        help=f"per-request timeout (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--user-agent", default=DEFAULT_USER_AGENT, help="User-Agent header to send"
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="skip TLS certificate verification (for staging hosts with self-signed certs)",
    )
    parser.add_argument(
        "--fail-on",
        choices=_FAIL_ON_CHOICES,
        metavar="SEVERITY",
        help="exit 1 if any finding is at least this severe: "
        + ", ".join(_FAIL_ON_CHOICES),
    )
    parser.add_argument("--no-color", action="store_true", help="disable coloured text output")
    parser.add_argument("--version", action="version", version=f"audit {__version__}")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    output_format = "html" if args.open_after and args.format == "text" else args.format

    if args.open_after and not args.out:
        args.out = "qa-report.html"

    try:
        result = audit_url(
            args.url,
            check_links=args.check_links,
            max_links=args.max_links,
            timeout=args.timeout,
            user_agent=args.user_agent,
            verify_tls=not args.insecure,
        )
    except FetchError as exc:
        print(f"error: could not fetch page — {exc}", file=sys.stderr)
        return EXIT_ERROR
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return EXIT_ERROR

    if output_format == "html":
        body = html_report.render(result)
    elif output_format == "json":
        body = json.dumps(result.to_dict(), indent=2)
    else:
        body = terminal_report.render(result, color=False if args.no_color else None)

    if args.out:
        path = Path(args.out)
        if path.parent != Path(""):
            path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        print(f"Wrote {output_format} report to {path.resolve()}", file=sys.stderr)
        print(
            f"Overall score {result.overall_score:.1f}/100 · "
            f"{sum(result.counts.values())} findings",
            file=sys.stderr,
        )
        if args.open_after:
            webbrowser.open(path.resolve().as_uri())
    else:
        # Avoid a UnicodeEncodeError on consoles using a legacy code page. Guarded because
        # a redirected stdout is not necessarily a TextIOWrapper.
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(errors="replace")
        print(body)

    if args.fail_on:
        threshold = _SEVERITY_RANK[Severity(args.fail_on)]
        if any(_SEVERITY_RANK[f.severity] <= threshold for f in result.findings):
            return EXIT_FINDINGS

    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
