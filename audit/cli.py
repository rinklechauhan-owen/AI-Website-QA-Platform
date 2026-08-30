"""Command line entry point: python -m audit <url>"""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path
from typing import List, Optional

from audit import __version__, inventory, server
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
        "  python -m audit --serve                              # paste URLs in a browser\n"
        "  python -m audit example.com\n"
        "  python -m audit https://example.com --format html --out report.html --open\n"
        "  python -m audit https://example.com --check-links --check-images\n"
        "  python -m audit https://example.com --fail-on high   # for CI\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "url",
        nargs="?",
        help="page to audit; the https:// scheme is added if omitted. Omit when using --serve",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="start a local web UI and open it, so URLs can be pasted into a browser",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=server.DEFAULT_PORT,
        metavar="N",
        help=f"port for --serve (default: {server.DEFAULT_PORT}; next free port if taken)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="with --serve, do not open a browser tab automatically",
    )
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
        "--crawl",
        action="store_true",
        help="crawl the whole website from this URL instead of auditing one page",
    )
    parser.add_argument(
        "--max-urls",
        type=int,
        default=None,
        metavar="N",
        help="with --crawl, the maximum URLs to visit (default: 2000)",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=None,
        metavar="N",
        help="with --crawl, how many links deep to go (default: unlimited)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        metavar="N",
        help="with --crawl, simultaneous requests (default: 5)",
    )
    parser.add_argument(
        "--ignore-robots",
        action="store_true",
        help="with --crawl, do not obey robots.txt",
    )
    parser.add_argument(
        "--check-images",
        action="store_true",
        help="measure every image's transfer size (one extra request per image)",
    )
    parser.add_argument(
        "--image-size-limit",
        type=float,
        default=2.5,
        metavar="MB",
        help="flag images heavier than this many megabytes (default: 2.5)",
    )
    parser.add_argument(
        "--content-tags",
        default=",".join(inventory.DEFAULT_CONTENT_TAGS),
        metavar="TAGS",
        help="comma-separated tags to list in the content section "
        f"(default: {','.join(inventory.DEFAULT_CONTENT_TAGS)})",
    )
    parser.add_argument(
        "--outline-depth",
        type=int,
        default=inventory.DEFAULT_MAX_OUTLINE_DEPTH,
        metavar="N",
        help=f"nesting depth shown in the structure outline "
        f"(default: {inventory.DEFAULT_MAX_OUTLINE_DEPTH})",
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
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.serve:
        return server.serve(
            port=args.port,
            open_browser=not args.no_browser,
        )

    if not args.url:
        parser.error("a url is required unless --serve is given")

    if args.crawl:
        return _run_crawl(args)

    output_format = "html" if args.open_after and args.format == "text" else args.format

    if args.open_after and not args.out:
        args.out = "qa-report.html"

    content_tags = [tag.strip().lower() for tag in args.content_tags.split(",") if tag.strip()]
    if not content_tags:
        parser.error("--content-tags needs at least one tag, e.g. h2,h3,p")

    try:
        result = audit_url(
            args.url,
            check_links=args.check_links,
            max_links=args.max_links,
            timeout=args.timeout,
            user_agent=args.user_agent,
            verify_tls=not args.insecure,
            content_tags=content_tags,
            outline_depth=args.outline_depth,
            check_images=args.check_images,
            image_size_limit=int(args.image_size_limit * 1024 * 1024),
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


def _run_crawl(args) -> int:
    """Crawl a whole site from the command line and print a summary."""
    from audit.crawl import export as crawl_export
    from audit.crawl.crawler import Crawler
    from audit.crawl.settings import DEFAULT_MAX_URLS, CrawlSettings
    from audit.crawl.store import CrawlStore

    settings = CrawlSettings(
        max_urls=args.max_urls or DEFAULT_MAX_URLS,
        max_depth=args.max_depth,
        concurrency=args.concurrency,
        timeout=args.timeout,
        user_agent=args.user_agent,
        verify_tls=not args.insecure,
        respect_robots=not args.ignore_robots,
        check_image_sizes=args.check_images,
        image_size_limit=int(args.image_size_limit * 1024 * 1024),
        check_external_links=args.check_links,
    )

    store = CrawlStore(":memory:")
    try:
        crawler = Crawler(args.url, settings, store)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    print(f"Crawling {crawler.root_url} (up to {settings.max_urls:,} URLs)...", file=sys.stderr)

    try:
        crawler.run()
    except KeyboardInterrupt:
        crawler.stop()
        print("\ninterrupted; stopping", file=sys.stderr)

    session_id = crawler.session_id
    progress = crawler.progress
    buckets = store.status_breakdown(session_id)
    session = store.get_session(session_id)

    if args.format == "json":
        payload = {
            "root_url": crawler.root_url,
            "progress": progress.to_dict(),
            "status_breakdown": buckets,
            "health_score": session.health_score,
            "issues": [dict(row) for row in store.issue_summary(session_id)],
        }
        body = json.dumps(payload, indent=2)
    elif args.format == "html":
        from audit.report import crawl_pages

        body = crawl_pages.dashboard(store, session_id, progress)
    else:
        lines = [
            "=" * 78,
            "  WEBSITE CRAWL",
            "=" * 78,
            f"  Site         {crawler.root_url}",
            f"  Crawled      {progress.crawled:,} of {progress.discovered:,} discovered",
            f"  Health       {session.health_score or 0:.0f}/100",
            f"  Elapsed      {progress.elapsed_s:.0f}s at {progress.urls_per_second} URL/s",
            "",
            f"  2xx {buckets['2xx']:,}   3xx {buckets['3xx']:,}   "
            f"4xx {buckets['4xx']:,}   5xx {buckets['5xx']:,}   failed {buckets['failed']:,}",
            "",
            "-" * 78,
            "  ISSUES",
            "-" * 78,
        ]
        for row in store.issue_summary(session_id)[:40]:
            lines.append(f"  {row['severity']:<9} {row['urls']:>6}  {row['title'][:55]}")
        lines.append("=" * 78)
        body = "\n".join(lines)

    if args.out:
        path = Path(args.out)
        if path.parent != Path(""):
            path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix.lower() == ".csv":
            path.write_text(
                crawl_export.collect(crawl_export.urls_csv(store, session_id)), encoding="utf-8"
            )
        else:
            path.write_text(body, encoding="utf-8")
        print(f"Wrote {path.resolve()}", file=sys.stderr)
    else:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(errors="replace")
        print(body)

    if args.fail_on:
        threshold = _SEVERITY_RANK[Severity(args.fail_on)]
        counts = store.severity_counts(session_id)
        for severity, rank in _SEVERITY_RANK.items():
            if rank <= threshold and counts.get(severity.value, 0):
                store.close()
                return EXIT_FINDINGS

    store.close()
    return EXIT_OK
