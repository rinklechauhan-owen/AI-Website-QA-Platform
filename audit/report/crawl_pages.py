"""Crawl screens, sharing the app shell and design system with the rest of the tool.

Server-rendered and script-free, like every other page here. The live progress screen refreshes
itself with `<meta http-equiv="refresh">` rather than polling from JavaScript, which keeps the
strict Content-Security-Policy intact; controls are ordinary form posts.

Large result sets are never rendered whole. Tables read one page of rows from the store, so a
2,000-URL crawl renders exactly as fast as a 50-URL one.
"""

from __future__ import annotations

from html import escape
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import quote, urlencode

from audit import __version__
from audit.crawl.crawler import CrawlProgress, CrawlState
from audit.crawl.settings import DEFAULT_MAX_URLS, CrawlSettings
from audit.crawl.store import SORTABLE_COLUMNS, CrawlStore
from audit.report.theme import BASE_CSS, icon, logo_img

PAGE_SIZE = 100

_CRAWL_CSS = """
.formwrap { max-width: 820px; }
.field { margin-bottom: 18px; }
.field > label { display: block; font-size: var(--fs-sm); font-weight: var(--fw-semibold);
                 margin-bottom: 7px; }
.field .help { font-size: var(--fs-sm); color: var(--ink-2); margin: 0 0 9px; }
input[type=url], input[type=text], input[type=number], select, textarea {
  width: 100%; padding: 12px 14px; font-size: var(--fs-base); border-radius: var(--r-md);
  border: 1px solid var(--border-strong); background: var(--surface); color: var(--ink);
  font-family: inherit;
}
input:focus, select:focus, textarea:focus { outline: 2px solid var(--accent);
                                            outline-offset: 1px; border-color: var(--accent); }
.opts { display: flex; flex-direction: column; gap: 11px; margin: 16px 0 22px; }
.opt { display: flex; gap: 10px; align-items: flex-start; font-size: var(--fs-sm);
       color: var(--ink-2); }
.opt input { margin-top: 3px; flex: 0 0 auto; }
.opt b { color: var(--ink); font-weight: var(--fw-semibold); }
.err { margin: 0 0 20px; padding: 13px 16px; border-radius: var(--r-md); font-size: var(--fs-sm);
       background: var(--surface); border: 1px solid var(--bad); color: var(--bad); }
.err b { display: block; margin-bottom: 3px; }

/* mode chooser */
.modes { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 14px;
         margin-bottom: 26px; }
.mode { display: block; text-decoration: none; color: inherit; background: var(--surface);
        border: 1px solid var(--border); border-radius: var(--r-lg); padding: 22px;
        box-shadow: var(--shadow-sm); }
.mode:hover { border-color: var(--accent); }
.mode .ic { width: 40px; height: 40px; border-radius: var(--r-md); display: flex;
            align-items: center; justify-content: center; background: var(--accent-soft);
            color: var(--accent); margin-bottom: 14px; }
.mode h3 { margin: 0 0 6px; font-size: var(--fs-md); font-weight: var(--fw-semibold); }
.mode p { margin: 0; font-size: var(--fs-sm); color: var(--ink-2); }

/* settings grid */
.settings-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                 gap: 14px; }

/* progress */
.progress-shell { max-width: 820px; }
.bar { height: 12px; border-radius: 999px; background: var(--border); overflow: hidden;
       margin: 16px 0 10px; }
.bar i { display: block; height: 100%; border-radius: 999px; background: var(--brand-grad); }
.progress-num { font-size: var(--fs-xl); font-weight: var(--fw-bold); letter-spacing: -.03em;
                font-variant-numeric: tabular-nums; }
.current { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
           font-size: var(--fs-xs); color: var(--ink-2); word-break: break-all;
           background: var(--surface-2); border: 1px solid var(--border);
           border-radius: var(--r-sm); padding: 10px 12px; margin-top: 14px; }
.controls { display: flex; gap: 9px; flex-wrap: wrap; margin-top: 20px; }
.controls form { margin: 0; }

/* tables */
.toolbar { display: flex; gap: 10px; flex-wrap: wrap; align-items: flex-end;
           margin-bottom: 16px; }
.toolbar .grow { flex: 1 1 220px; }
.toolbar label { display: block; font-size: var(--fs-xs); font-weight: var(--fw-semibold);
                 color: var(--ink-2); margin-bottom: 5px; }
.toolbar input, .toolbar select { padding: 8px 11px; font-size: var(--fs-sm); }
table.grid th a { color: inherit; text-decoration: none; white-space: nowrap; }
table.grid th a:hover { color: var(--accent); }
table.grid td.num { text-align: right; font-variant-numeric: tabular-nums; }
.pill-status { display: inline-block; padding: 2px 8px; border-radius: 5px;
               font-size: var(--fs-xs); font-weight: var(--fw-bold); color: #fff; }
.s2xx { background: var(--good); } .s3xx { background: var(--medium); }
.s4xx { background: var(--high); } .s5xx { background: var(--critical); }
.sfail { background: var(--info); }
@media (prefers-color-scheme: dark) { .pill-status { color: #0b0f16; } }
.pager { display: flex; gap: 8px; align-items: center; justify-content: space-between;
         margin-top: 16px; flex-wrap: wrap; font-size: var(--fs-sm); color: var(--ink-2); }
.pager a { display: inline-block; padding: 7px 13px; border: 1px solid var(--border-strong);
           border-radius: 999px; text-decoration: none; color: var(--ink);
           font-weight: var(--fw-semibold); }
.pager a:hover { background: var(--surface-2); }
.pager .off { opacity: .4; pointer-events: none; }
.truncate { max-width: 380px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
            display: inline-block; vertical-align: bottom; }

/* issue list */
.issues { display: flex; flex-direction: column; gap: 8px; }
.issue-row { display: flex; align-items: center; gap: 12px; padding: 13px 16px;
             background: var(--surface); border: 1px solid var(--border);
             border-left: 3px solid var(--border); border-radius: var(--r-md);
             text-decoration: none; color: inherit; }
.issue-row:hover { border-color: var(--accent); }
.issue-row.critical { border-left-color: var(--critical); }
.issue-row.high { border-left-color: var(--high); }
.issue-row.medium { border-left-color: var(--medium); }
.issue-row.low { border-left-color: var(--low); }
.issue-row.info { border-left-color: var(--info); }
.issue-row .t { flex: 1 1 auto; min-width: 0; font-size: var(--fs-sm);
                font-weight: var(--fw-medium); }
.issue-row .r { font-size: var(--fs-xs); color: var(--ink-3);
                font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
.issue-row .n { font-weight: var(--fw-bold); font-variant-numeric: tabular-nums;
                min-width: 46px; text-align: right; }

.kv { display: grid; grid-template-columns: minmax(120px, 200px) 1fr; gap: 8px 16px;
      font-size: var(--fs-sm); }
.kv dt { color: var(--ink-2); }
.kv dd { margin: 0; word-break: break-all; font-weight: var(--fw-medium); }
.exports { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 14px; }
.banner { display: flex; gap: 14px; align-items: flex-start; padding: 16px 18px;
          border-radius: var(--r-lg); background: var(--surface); margin-bottom: 18px;
          border: 1px solid var(--medium); border-left: 4px solid var(--medium); }
.banner .ic { color: var(--medium); flex: 0 0 auto; margin-top: 1px; }
.banner h4 { margin: 0 0 5px; font-size: var(--fs-sm); font-weight: var(--fw-semibold); }
.banner p { margin: 0; font-size: var(--fs-sm); color: var(--ink-2); }
.banner a { font-weight: var(--fw-semibold); }
"""



def issue_label(rule: str, fallback: str = "") -> str:
    """A label for a group of findings sharing one rule.

    The stored title describes a single instance ("Sitemap lists a URL returning 404: /x"),
    so using one row's title as the heading for a whole group states something false about
    every other URL in it. The rule id is generic by construction, so it is humanised instead.
    """
    _, _, tail = rule.partition(".")
    if not tail:
        return fallback or rule
    words = tail.replace("-", " ").strip()
    return (words[:1].upper() + words[1:]) if words else (fallback or rule)


def _shell(
    *,
    title: str,
    page_title: str,
    crumb: str,
    subtitle: str,
    body: str,
    active: str = "",
    actions: str = "",
    session_id: Optional[int] = None,
    refresh: Optional[int] = None,
) -> str:
    nav: List[tuple] = [
        ("/", "New audit", "search"),
        ("/crawl", "Crawl a website", "layers"),
        ("/schema", "Schema Generator", "wand"),
    ]
    groups: List[str] = ['<p class="navgroup">Tools</p>']
    groups += [
        f'    <a class="navitem{" active" if href == active else ""}" href="{href}">'
        f'{icon(name)}<span class="navlabel">{escape(label)}</span></a>'
        for href, label, name in nav
    ]

    if session_id is not None:
        groups.append('<p class="navgroup">This crawl</p>')
        for href, label, name in (
            (f"/crawl/{session_id}", "Dashboard", "dashboard"),
            (f"/crawl/{session_id}/urls", "All URLs", "layers"),
            (f"/crawl/{session_id}/issues", "Issues", "alert"),
            (f"/crawl/{session_id}/links", "Links", "link"),
            (f"/crawl/{session_id}/technical", "Robots & Sitemap", "eye"),
        ):
            groups.append(
                f'    <a class="navitem{" active" if href == active else ""}" href="{href}">'
                f'{icon(name)}<span class="navlabel">{escape(label)}</span></a>'
            )

    meta_refresh = (
        f'<meta http-equiv="refresh" content="{refresh}">' if refresh else ""
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{meta_refresh}
<title>{escape(title)}</title>
<style>{BASE_CSS}{_CRAWL_CSS}
.navitem.active {{ background: var(--accent-soft); color: var(--accent);
                   font-weight: var(--fw-semibold); }}
</style>
</head>
<body>
<div class="app">
  <aside class="sidebar">
    <div class="brand">
      {logo_img(26)}
      <span class="brand-sub">Website QA &middot; Audit toolkit</span>
    </div>
{chr(10).join(groups)}
    <div class="sidefoot">
      <div class="sidecard">
        <h4>Nothing is stored</h4>
        <p>Crawls live in memory while the tool is open. No account, no database, no file.</p>
        <code>v{escape(__version__)}</code>
      </div>
    </div>
  </aside>

  <div class="main">
    <header class="topbar">
      <div class="topbar-main">
        <p class="crumb">{escape(crumb)}</p>
        <h1>{escape(page_title)}</h1>
        <p class="sub">{subtitle}</p>
      </div>
      <div class="topbar-side">{actions}</div>
    </header>
    <div class="content">
{body}
    </div>
  </div>
</div>
</body>
</html>
"""


# --- mode chooser ----------------------------------------------------------------------


def mode_chooser() -> str:
    """Shown above the single-page form so both modes are visible from the front door."""
    return f"""      <div class="modes">
        <a class="mode" href="/">
          <span class="ic">{icon("search", 20)}</span>
          <h3>Single Page Audit</h3>
          <p>Audit one URL in full: SEO, headings, meta tags, canonical, images and schema.</p>
        </a>
        <a class="mode" href="/crawl">
          <span class="ic">{icon("layers", 20)}</span>
          <h3>Full Website Crawl</h3>
          <p>Follow internal links across the whole site, up to {DEFAULT_MAX_URLS:,} pages,
          and find site-wide problems like duplicates and broken links.</p>
        </a>
      </div>"""


# --- crawl settings --------------------------------------------------------------------


def _checkbox(name: str, label: str, description: str, checked: bool) -> str:
    return f"""              <label class="opt">
                <input type="checkbox" name="{name}" value="1"{" checked" if checked else ""}>
                <span><b>{escape(label)}</b> — {description}</span>
              </label>"""


def crawl_form(error: Optional[str] = None, url_value: str = "") -> str:
    settings = CrawlSettings()
    error_block = (
        f'<p class="err"><b>Could not start that crawl</b>{escape(error)}</p>' if error else ""
    )

    body = f"""      <div class="formwrap">
        {error_block}
        <div class="card card-pad">
          <form method="post" action="/crawl">
            <div class="field">
              <label for="url">Website root URL</label>
              <p class="help">Start from the home page. The crawler follows internal links
              from here.</p>
              <input id="url" name="url" type="url" required autofocus
                     placeholder="https://example.com"
                     value="{escape(url_value, quote=True)}">
            </div>

            <div class="settings-grid">
              <div class="field">
                <label for="max_urls">Maximum URLs</label>
                <input id="max_urls" name="max_urls" type="number" min="1" max="50000"
                       value="{settings.max_urls}">
              </div>
              <div class="field">
                <label for="max_depth">Crawl depth</label>
                <input id="max_depth" name="max_depth" type="number" min="0" max="20"
                       placeholder="Unlimited">
              </div>
              <div class="field">
                <label for="concurrency">Concurrent requests</label>
                <input id="concurrency" name="concurrency" type="number" min="1" max="20"
                       value="{settings.concurrency}">
              </div>
              <div class="field">
                <label for="delay_ms">Delay between requests (ms)</label>
                <input id="delay_ms" name="delay_ms" type="number" min="0" max="10000"
                       value="{settings.delay_ms}">
              </div>
            </div>

            <div class="field">
              <label for="exclude_patterns">Exclude URLs containing</label>
              <p class="help">One pattern per line, or comma separated. Wildcards allowed.</p>
              <input id="exclude_patterns" name="exclude_patterns" type="text"
                     placeholder="/tag/, /cart, *?replytocom=*">
            </div>
            <div class="field">
              <label for="include_patterns">Only crawl URLs containing</label>
              <p class="help">Leave empty to crawl the whole site.</p>
              <input id="include_patterns" name="include_patterns" type="text"
                     placeholder="/blog/">
            </div>

            <div class="opts">
{_checkbox("respect_robots", "Respect robots.txt", "Obey the site's crawl rules. Turning this off may fetch pages the owner asked crawlers to leave alone.", settings.respect_robots)}
{_checkbox("follow_redirects", "Follow redirects", "Follow 301 and 302 responses to their destination and record the chain.", settings.follow_redirects)}
{_checkbox("crawl_subdomains", "Crawl subdomains", "Treat blog.example.com as part of example.com.", settings.crawl_subdomains)}
{_checkbox("check_external_links", "Check external links", "Verify that outbound links still resolve. Makes extra requests to other sites.", settings.check_external_links)}
{_checkbox("check_image_sizes", "Check image sizes", "Measure every image to find any over 2.5&nbsp;MB. Slow on image-heavy sites.", settings.check_image_sizes)}
{_checkbox("include_pdfs", "Include PDFs", "Crawl linked PDF documents as well as HTML pages.", settings.include_pdfs)}
{_checkbox("ignore_query", "Ignore query strings", "Treat /page?a=1 and /page as the same URL.", settings.ignore_query)}
{_checkbox("discover_sitemaps", "Find and use sitemaps", "Read sitemap.xml and crawl anything listed there too.", settings.discover_sitemaps)}
            </div>

            <button class="btn primary" type="submit"
                    style="width:100%;justify-content:center">Start crawl</button>
          </form>
        </div>
        <p class="section-note" style="margin-top:18px">Crawls run in memory and are not saved.
        Close the tool and the results are gone — export to CSV to keep them. Analyses the
        served HTML, so JavaScript-rendered content is not included.</p>
      </div>"""

    return _shell(
        title="Full Website Crawl",
        page_title="Full Website Crawl",
        crumb="Website QA",
        subtitle="Crawl a whole site and find issues no single-page audit can see.",
        body=body,
        active="/crawl",
    )


# --- live progress ---------------------------------------------------------------------


def _control(session_id: int, action: str, label: str, primary: bool = False) -> str:
    return (
        f'<form method="post" action="/crawl/{session_id}/{action}">'
        f'<button class="btn{" primary" if primary else ""}" type="submit">{escape(label)}</button>'
        "</form>"
    )


def progress_page(progress: CrawlProgress, settings: CrawlSettings) -> str:
    running = progress.state in (CrawlState.RUNNING, CrawlState.PREPARING)
    paused = progress.state is CrawlState.PAUSED

    controls = []
    if running:
        controls.append(_control(progress.session_id, "pause", "Pause"))
    if paused:
        controls.append(_control(progress.session_id, "resume", "Resume", primary=True))
    if not progress.state.is_finished:
        controls.append(_control(progress.session_id, "stop", "Stop crawl"))
    else:
        controls.append(
            f'<a class="btn primary" href="/crawl/{progress.session_id}">View results</a>'
        )

    stats = [
        ("Discovered URLs", f"{progress.discovered:,}"),
        ("Crawled URLs", f"{progress.crawled:,}"),
        ("Remaining", f"{progress.remaining:,}"),
        ("In flight", f"{progress.in_flight:,}"),
        ("Errors", f"{progress.errors:,}"),
        ("Warnings", f"{progress.warnings:,}"),
        ("Redirects", f"{progress.redirects:,}"),
        ("Speed", f"{progress.urls_per_second} URL/s"),
        ("Estimated remaining", progress.eta_label),
    ]
    rows = "".join(
        f'<li><span class="fk">{escape(label)}</span>'
        f'<span class="fv">{escape(value)}</span></li>'
        for label, value in stats
    )

    message = (
        f'<p class="section-note" style="margin-top:14px">{escape(progress.message)}</p>'
        if progress.message
        else ""
    )

    body = f"""      <div class="progress-shell">
        <div class="card card-pad">
          <div class="card-head">
            <h3 class="card-title">{escape(progress.state.label)}</h3>
            <p class="card-note">{escape(progress.root_url)}</p>
          </div>

          <div class="progress-num">{progress.crawled:,} / {progress.max_urls:,}
            <span style="font-size:var(--fs-sm);color:var(--ink-2);font-weight:400">
              URLs crawled &middot; {progress.percent}%</span>
          </div>
          <div class="bar"><i style="width:{progress.percent}%"></i></div>

          <ul class="factlist">{rows}</ul>

          <div class="current"><b>Current URL</b><br>{escape(progress.current_url or "—")}</div>
          {message}
          <div class="controls">{"".join(controls)}</div>
        </div>
        <p class="section-note" style="margin-top:16px">This page refreshes itself every two
        seconds. The crawl continues whether or not this window is open.</p>
      </div>"""

    return _shell(
        title=f"Crawling {progress.root_url}",
        page_title="Crawl in progress",
        crumb="Full Website Crawl",
        subtitle=escape(progress.root_url),
        body=body,
        session_id=progress.session_id,
        # Only poll while there is something to see; a finished crawl stops reloading.
        refresh=2 if not progress.state.is_finished else None,
    )


# --- dashboard -------------------------------------------------------------------------


def _stat(label: str, value: str, note: str = "", accent: bool = False) -> str:
    return (
        f'<div class="stat{" accent" if accent else ""}">'
        f'<p class="k">{escape(label)}</p>'
        f'<p class="v">{escape(value)}</p>'
        f'<p class="d">{escape(note)}</p></div>'
    )


def _severity_class(code) -> str:
    if code is None:
        return "sfail"
    if 200 <= code < 300:
        return "s2xx"
    if 300 <= code < 400:
        return "s3xx"
    if 400 <= code < 500:
        return "s4xx"
    return "s5xx"


def dashboard(
    store: CrawlStore,
    session_id: int,
    progress: Optional[CrawlProgress] = None,
) -> str:
    session = store.get_session(session_id)
    buckets = store.status_breakdown(session_id)
    severities = store.severity_counts(session_id)
    crawled = store.count_urls(session_id)
    issues = store.issue_summary(session_id)

    critical = severities.get("critical", 0) + severities.get("high", 0)
    warnings = severities.get("medium", 0) + severities.get("low", 0)
    healthy = store.count_urls(
        session_id, "status_code >= 200 AND status_code < 300 AND issue_count = 0"
    )

    rendered = store.count_urls(session_id, "client_rendered = 1")
    banner = ""
    if rendered:
        share = round(rendered / max(crawled, 1) * 100)
        banner = (
            f'<div class="banner"><span class="ic">{icon("alert", 20)}</span><div>'
            f"<h4>{rendered:,} of {crawled:,} pages ({share}%) build their content in the "
            "browser</h4>"
            "<p>This audit reads the HTML the server sends, which is what a crawler sees "
            "before any script runs. On those pages, findings like missing headings or thin "
            "content may describe what this tool cannot see rather than a real problem. "
            f'<a href="/crawl/{session_id}/issues/site.javascript-rendered">See which pages</a>'
            ", and confirm anything important with Google Search Console&rsquo;s URL "
            "Inspection, which shows the rendered page.</p></div></div>"
        )

    cards = "".join(
        [
            _stat("Pages crawled", f"{crawled:,}", f"of {session.urls_discovered:,} discovered",
                  accent=True),
            _stat("Health score", f"{session.health_score or 0:.0f}", "average page score"),
            _stat("Errors", f"{critical:,}", "critical and high severity"),
            _stat("Warnings", f"{warnings:,}", "medium and low severity"),
        ]
    )

    status_rows = "".join(
        f'<li><span class="fk">{escape(label)}</span>'
        f'<span class="fv">{buckets.get(key, 0):,}</span></li>'
        for key, label in (
            ("2xx", "2xx — OK"),
            ("3xx", "3xx — Redirects"),
            ("4xx", "4xx — Client errors"),
            ("5xx", "5xx — Server errors"),
            ("failed", "Failed to respond"),
        )
    )

    quick_counts = [
        ("Missing titles", "title IS NULL OR title = ''"),
        ("Missing meta descriptions", "meta_description IS NULL OR meta_description = ''"),
        ("Missing H1", "h1_count = 0"),
        ("Multiple H1s", "h1_count > 1"),
        ("Missing canonical", "canonical IS NULL OR canonical = ''"),
        ("Non-indexable", "indexable = 0"),
        ("Images missing alt", "missing_alt > 0"),
        ("Low word count", "word_count < 200 AND word_count IS NOT NULL"),
    ]
    quick_rows = "".join(
        f'<li><span class="fk">{escape(label)}</span>'
        f'<span class="fv">{store.count_urls(session_id, where):,}</span></li>'
        for label, where in quick_counts
    )

    issue_rows = "".join(
        f'<a class="issue-row {escape(row["severity"])}" '
        f'href="/crawl/{session_id}/issues/{quote(row["rule"])}" '
        f'title="{escape(row["title"], quote=True)}">'
        f'<span class="t">{escape(issue_label(row["rule"], row["title"]))}</span>'
        f'<span class="r">{escape(row["rule"])}</span>'
        f'<span class="n">{row["urls"]:,}</span></a>'
        for row in issues[:25]
    ) or '<div class="clean">No issues found across the crawl.</div>'

    depth_rows = "".join(
        f'<li><span class="fk">Depth {depth}</span><span class="fv">{count:,}</span></li>'
        for depth, count in sorted(store.depth_breakdown(session_id).items())
    )

    body = f"""{banner}
      <div class="grid-4">{cards}</div>

      <div class="grid-2">
        <div class="card card-pad">
          <div class="card-head">
            <h3 class="card-title">Issues found</h3>
            <p class="card-note">Click any issue to see the URLs it affects</p>
          </div>
          <div class="issues">{issue_rows}</div>
          {f'<p class="card-note" style="margin-top:14px">Showing 25 of {len(issues)}. '
           f'<a href="/crawl/{session_id}/issues">See all</a>.</p>' if len(issues) > 25 else ""}
        </div>

        <div>
          <div class="card card-pad">
            <div class="card-head"><h3 class="card-title">Response codes</h3></div>
            <ul class="factlist">{status_rows}</ul>
          </div>
          <div class="card card-pad" style="margin-top:14px">
            <div class="card-head"><h3 class="card-title">Crawl depth</h3></div>
            <ul class="factlist">{depth_rows or "<li>No pages</li>"}</ul>
          </div>
        </div>
      </div>

      <div class="grid-2">
        <div class="card card-pad">
          <div class="card-head"><h3 class="card-title">At a glance</h3></div>
          <ul class="factlist">{quick_rows}</ul>
        </div>
        <div class="card card-pad">
          <div class="card-head"><h3 class="card-title">Export</h3></div>
          <p class="card-note">Crawls are not saved. Export anything you need to keep.</p>
          <div class="exports">
            <a class="btn" href="/crawl/{session_id}/export/urls">All URLs</a>
            <a class="btn" href="/crawl/{session_id}/export/issues">All issues</a>
            <a class="btn" href="/crawl/{session_id}/export/links">All links</a>
            <a class="btn" href="/crawl/{session_id}/export/broken-links">Broken links</a>
          </div>
        </div>
      </div>"""

    return _shell(
        title=f"Crawl results — {session.root_url}",
        page_title="Website SEO Audit",
        crumb="Crawl results",
        subtitle=f'<a href="{escape(session.root_url)}">{escape(session.root_url)}</a>'
        f' &middot; {escape(session.status)}',
        body=body,
        active=f"/crawl/{session_id}",
        session_id=session_id,
        actions=f'<a class="btn" href="/crawl/{session_id}/urls">All URLs</a>'
        f'<a class="btn primary" href="/crawl">New crawl</a>',
    )


# --- URL table -------------------------------------------------------------------------

TABLE_COLUMNS: List[tuple] = [
    ("url", "URL", False),
    ("status_code", "Status", True),
    ("indexable", "Indexability", False),
    ("title", "Title", False),
    ("title_length", "Title Len", True),
    ("meta_length", "Meta Len", True),
    ("h1_count", "H1s", True),
    ("word_count", "Words", True),
    ("internal_links", "In-links", True),
    ("external_links", "Ext", True),
    ("images", "Imgs", True),
    ("missing_alt", "No ALT", True),
    ("depth", "Depth", True),
    ("issue_count", "Issues", True),
]

FILTERS: Dict[str, tuple] = {
    "all": ("All URLs", "", ()),
    "2xx": ("2xx OK", "status_code >= 200 AND status_code < 300", ()),
    "3xx": ("3xx Redirects", "redirect_hops > 0", ()),
    "4xx": ("4xx Errors", "status_code >= 400 AND status_code < 500", ()),
    "5xx": ("5xx Errors", "status_code >= 500", ()),
    "failed": ("Failed", "status_code IS NULL", ()),
    "noindex": ("Non-indexable", "indexable = 0", ()),
    "no-title": ("Missing title", "title IS NULL OR title = ''", ()),
    "no-meta": ("Missing meta", "meta_description IS NULL OR meta_description = ''", ()),
    "no-h1": ("Missing H1", "h1_count = 0", ()),
    "multi-h1": ("Multiple H1s", "h1_count > 1", ()),
    "no-canonical": ("Missing canonical", "canonical IS NULL OR canonical = ''", ()),
    "missing-alt": ("Images missing ALT", "missing_alt > 0", ()),
    "thin": ("Low word count", "word_count < 200 AND word_count IS NOT NULL", ()),
    "not-in-sitemap": ("Not in sitemap", "in_sitemap = 0", ()),
}


def _query_string(**params) -> str:
    clean = {k: v for k, v in params.items() if v not in ("", None, 0, False)}
    return ("?" + urlencode(clean)) if clean else ""


def url_table(
    store: CrawlStore,
    session_id: int,
    *,
    page: int = 1,
    sort: str = "url",
    descending: bool = False,
    search: str = "",
    filter_key: str = "all",
) -> str:
    session = store.get_session(session_id)
    label, where, params = FILTERS.get(filter_key, FILTERS["all"])

    total = store.count_urls(session_id, where, params) if where else store.count_urls(session_id)
    if search:
        total = None  # Counting a search would need the same LIKE twice; page it instead.

    page = max(1, page)
    offset = (page - 1) * PAGE_SIZE
    rows = store.urls_page(
        session_id,
        limit=PAGE_SIZE,
        offset=offset,
        sort=sort,
        descending=descending,
        where=where,
        params=params,
        search=search,
    )

    def header(column: str, title: str) -> str:
        if column not in SORTABLE_COLUMNS:
            return f"<th>{escape(title)}</th>"
        flip = "1" if (sort == column and not descending) else ""
        arrow = " ▾" if (sort == column and descending) else (" ▴" if sort == column else "")
        link = _query_string(
            page=page, sort=column, desc=flip, q=search,
            filter=filter_key if filter_key != "all" else "",
        )
        return f'<th><a href="/crawl/{session_id}/urls{link}">{escape(title)}{arrow}</a></th>'

    head = "".join(header(column, title) for column, title, _ in TABLE_COLUMNS)

    body_rows = []
    for row in rows:
        status = row["status_code"]
        cells = [
            f'<td><a href="/crawl/{session_id}/url/{row["id"]}" class="truncate" '
            f'title="{escape(row["url"], quote=True)}">{escape(row["url"])}</a></td>',
            f'<td><span class="pill-status {_severity_class(status)}">'
            f'{status if status else "fail"}</span></td>',
            f'<td>{"Indexable" if row["indexable"] else "No" if row["indexable"] == 0 else "—"}</td>',
            f'<td><span class="truncate" style="max-width:240px">'
            f'{escape(row["title"] or "")}</span></td>',
        ]
        for column in ("title_length", "meta_length", "h1_count", "word_count",
                       "internal_links", "external_links", "images", "missing_alt",
                       "depth", "issue_count"):
            value = row[column]
            cells.append(f'<td class="num">{"" if value is None else value}</td>')
        body_rows.append("<tr>" + "".join(cells) + "</tr>")

    filter_options = "".join(
        f'<option value="{key}"{" selected" if key == filter_key else ""}>'
        f"{escape(text)}</option>"
        for key, (text, _, _) in FILTERS.items()
    )

    has_next = len(rows) == PAGE_SIZE
    prev_link = _query_string(page=page - 1, sort=sort, desc="1" if descending else "",
                              q=search, filter=filter_key if filter_key != "all" else "")
    next_link = _query_string(page=page + 1, sort=sort, desc="1" if descending else "",
                              q=search, filter=filter_key if filter_key != "all" else "")

    shown = f"{offset + 1:,}–{offset + len(rows):,}" if rows else "0"
    count_label = f"of {total:,}" if total is not None else ""

    body = f"""      <form class="toolbar" method="get" action="/crawl/{session_id}/urls">
        <div class="grow">
          <label for="q">Search URL, title or description</label>
          <input id="q" name="q" type="text" value="{escape(search, quote=True)}"
                 placeholder="/services">
        </div>
        <div>
          <label for="filter">Filter</label>
          <select id="filter" name="filter">{filter_options}</select>
        </div>
        <div><button class="btn primary" type="submit">Apply</button></div>
        <div><a class="btn" href="/crawl/{session_id}/urls">Reset</a></div>
      </form>

      <div class="scroll-x"><table class="grid">
        <tr>{head}</tr>
        {"".join(body_rows) or '<tr><td colspan="14">No URLs match.</td></tr>'}
      </table></div>

      <div class="pager">
        <span>Showing {shown} {count_label} &middot; {escape(label)}</span>
        <span>
          <a class="{"off" if page <= 1 else ""}"
             href="/crawl/{session_id}/urls{prev_link}">Previous</a>
          <a class="{"off" if not has_next else ""}"
             href="/crawl/{session_id}/urls{next_link}">Next</a>
        </span>
      </div>

      <div class="exports">
        <a class="btn" href="/crawl/{session_id}/export/urls">Export all URLs (CSV)</a>
      </div>"""

    return _shell(
        title=f"URLs — {session.root_url}",
        page_title="All URLs",
        crumb="Crawl results",
        subtitle=f"{escape(label)} &middot; {escape(session.root_url)}",
        body=body,
        active=f"/crawl/{session_id}/urls",
        session_id=session_id,
    )


# --- issues ----------------------------------------------------------------------------


def issue_list(store: CrawlStore, session_id: int) -> str:
    session = store.get_session(session_id)
    issues = store.issue_summary(session_id)

    rows = "".join(
        f'<a class="issue-row {escape(row["severity"])}" '
        f'href="/crawl/{session_id}/issues/{quote(row["rule"])}" '
        f'title="{escape(row["title"], quote=True)}">'
        f'<span class="t">{escape(issue_label(row["rule"], row["title"]))}</span>'
        f'<span class="r">{escape(row["rule"])}</span>'
        f'<span class="n">{row["urls"]:,}</span></a>'
        for row in issues
    ) or '<div class="clean">No issues found across the crawl.</div>'

    body = f"""      <p class="section-note">Every issue found, most severe first, with the number
      of URLs affected. Click one to see only those URLs.</p>
      <div class="issues">{rows}</div>
      <div class="exports">
        <a class="btn" href="/crawl/{session_id}/export/issues">Export all issues (CSV)</a>
      </div>"""

    return _shell(
        title=f"Issues — {session.root_url}",
        page_title="Issues",
        crumb="Crawl results",
        subtitle=f"{len(issues)} distinct issues &middot; {escape(session.root_url)}",
        body=body,
        active=f"/crawl/{session_id}/issues",
        session_id=session_id,
    )


def issue_detail(store: CrawlStore, session_id: int, rule: str, page: int = 1) -> str:
    session = store.get_session(session_id)
    total = store.count_urls_with_issue(session_id, rule)
    offset = (max(1, page) - 1) * PAGE_SIZE
    rows = store.urls_with_issue(session_id, rule, limit=PAGE_SIZE, offset=offset)

    summary = next(
        (row for row in store.issue_summary(session_id) if row["rule"] == rule), None
    )
    title = issue_label(rule, summary["title"] if summary else rule)
    example = summary["title"] if summary else ""

    table_rows = "".join(
        f"<tr><td>"
        + (
            f'<a href="/crawl/{session_id}/url/{row["url_id"]}">{escape(row["url"])}</a>'
            if row["url_id"]
            else escape(row["url"])
        )
        + f'</td><td><span class="pill-status {_severity_class(row["status_code"])}">'
        f'{row["status_code"] or "—"}</span></td>'
        f'<td><span class="truncate">{escape(row["title"] or "")}</span></td></tr>'
        for row in rows
    )

    has_next = len(rows) == PAGE_SIZE
    body = f"""      <p class="section-note">Example: {escape(example)}</p>
      <div class="scroll-x"><table class="grid">
        <tr><th>URL</th><th>Status</th><th>Title</th></tr>
        {table_rows or '<tr><td colspan="3">No URLs.</td></tr>'}
      </table></div>
      <div class="pager">
        <span>Showing {offset + 1:,}–{offset + len(rows):,} of {total:,}</span>
        <span>
          <a class="{"off" if page <= 1 else ""}"
             href="/crawl/{session_id}/issues/{quote(rule)}?page={page - 1}">Previous</a>
          <a class="{"off" if not has_next else ""}"
             href="/crawl/{session_id}/issues/{quote(rule)}?page={page + 1}">Next</a>
        </span>
      </div>
      <div class="exports">
        <a class="btn" href="/crawl/{session_id}/export/issue?rule={quote(rule)}">
          Export these {total:,} URLs (CSV)</a>
        <a class="btn" href="/crawl/{session_id}/issues">All issues</a>
      </div>"""

    return _shell(
        title=f"{rule} — {session.root_url}",
        page_title=title,
        crumb="Issue",
        subtitle=f"{total:,} URLs affected &middot; <code>{escape(rule)}</code>",
        body=body,
        active=f"/crawl/{session_id}/issues",
        session_id=session_id,
    )


# --- URL detail ------------------------------------------------------------------------


def url_detail(store: CrawlStore, session_id: int, url_id: int) -> str:
    session = store.get_session(session_id)
    row = store.get_url(session_id, url_id)
    if row is None:
        return _shell(
            title="Not found",
            page_title="URL not found",
            crumb="Crawl results",
            subtitle="",
            body='<div class="clean">That URL is not part of this crawl.</div>',
            session_id=session_id,
        )

    payload = store.result_for(session_id, url_id) or {}
    findings = [
        finding
        for pack in payload.get("packs", [])
        for finding in pack.get("findings", [])
    ]

    basics = [
        ("URL", row["url"]),
        ("Status", str(row["status_code"] or row["error"] or "no response")),
        ("Final URL", row["final_url"] or "—"),
        ("Redirect hops", str(row["redirect_hops"])),
        ("Content type", row["content_type"] or "—"),
        ("Crawl depth", str(row["depth"])),
        ("Response time", f'{row["response_ms"]} ms' if row["response_ms"] else "—"),
        ("Size", f'{(row["byte_size"] or 0) / 1024:.1f} KB'),
        ("Indexability", "Indexable" if row["indexable"] else "Not indexable"),
        ("Robots directives", row["robots_directives"] or "—"),
        ("In sitemap", "Yes" if row["in_sitemap"] else "No"),
        ("Discovered from", row["discovered_from"] or "Start URL"),
        ("Page score", f'{row["score"]:.0f}/100' if row["score"] is not None else "—"),
    ]
    metadata = [
        ("Title", row["title"] or "(missing)"),
        ("Title length", str(row["title_length"] or 0)),
        ("Meta description", row["meta_description"] or "(missing)"),
        ("Meta length", str(row["meta_length"] or 0)),
        ("Canonical", row["canonical"] or "(missing)"),
        ("H1", row["h1"] or "(missing)"),
        ("H1 count", str(row["h1_count"] or 0)),
        ("Word count", str(row["word_count"] or 0)),
        ("Hreflang", row["hreflang"] or "—"),
        ("Schema", row["schema_types"] or "none"),
        ("Internal links", str(row["internal_links"] or 0)),
        ("External links", str(row["external_links"] or 0)),
        ("Images", str(row["images"] or 0)),
        ("Images missing ALT", str(row["missing_alt"] or 0)),
    ]

    def definition_list(pairs) -> str:
        return "".join(
            f"<dt>{escape(label)}</dt><dd>{escape(str(value))}</dd>" for label, value in pairs
        )

    finding_blocks = "".join(
        f'<article class="finding {escape(f.get("severity", "info"))}">'
        f'<div class="f-top">'
        f'<span class="badge {escape(f.get("severity", "info"))}">'
        f'{escape(str(f.get("severity", "")).title())}</span>'
        f'<span class="f-title">{escape(f.get("title", ""))}</span>'
        f'<span class="f-rule">{escape(f.get("rule", ""))}</span></div>'
        + (f'<p class="f-detail">{escape(f["detail"])}</p>' if f.get("detail") else "")
        + (
            f'<p class="f-fix"><b>Fix:</b> {escape(f["recommendation"])}</p>'
            if f.get("recommendation")
            else ""
        )
        + "</article>"
        for f in findings
    ) or '<div class="clean"><b>&#10003; Clean.</b> No issues found on this page.</div>'

    body = f"""      <div class="grid-2">
        <div class="card card-pad">
          <div class="card-head"><h3 class="card-title">Basic information</h3></div>
          <dl class="kv">{definition_list(basics)}</dl>
        </div>
        <div class="card card-pad">
          <div class="card-head"><h3 class="card-title">Metadata</h3></div>
          <dl class="kv">{definition_list(metadata)}</dl>
        </div>
      </div>

      <section style="margin-top:22px">
        <h2>Issues on this page <span class="count-pill">{len(findings)}</span></h2>
        <p class="section-note">Found by the same analysis the single-page audit runs.</p>
        {finding_blocks}
      </section>

      <div class="exports">
        <a class="btn primary" href="/?url={quote(row["url"])}&amp;check_images=1">
          Run the full single-page audit</a>
        <a class="btn" href="/crawl/{session_id}/urls">Back to all URLs</a>
      </div>"""

    return _shell(
        title=f"{row['url']}",
        page_title="URL detail",
        crumb="Crawl results",
        subtitle=f'<a href="{escape(row["url"])}">{escape(row["url"])}</a>',
        body=body,
        session_id=session_id,
    )


# --- links and technical ---------------------------------------------------------------


def links_page(store: CrawlStore, session_id: int, page: int = 1) -> str:
    session = store.get_session(session_id)
    statuses = store.url_status_map(session_id)
    offset = (max(1, page) - 1) * PAGE_SIZE

    rows = store._query(  # noqa: SLF001 - paginated read of the link table
        "SELECT * FROM crawl_link WHERE session_id = ? ORDER BY id LIMIT ? OFFSET ?",
        (session_id, PAGE_SIZE, offset),
    )

    table_rows = "".join(
        f'<tr><td><span class="truncate">{escape(row["source_url"])}</span></td>'
        f'<td><span class="truncate">{escape(row["target_url"])}</span></td>'
        f'<td>{"Internal" if row["is_internal"] else "External"}</td>'
        f'<td><span class="truncate" style="max-width:200px">'
        f'{escape(row["anchor_text"] or "")}</span></td>'
        f'<td><span class="pill-status '
        f'{_severity_class(row["status_code"] or statuses.get(row["target_url"]))}">'
        f'{row["status_code"] or statuses.get(row["target_url"]) or "—"}</span></td></tr>'
        for row in rows
    )

    has_next = len(rows) == PAGE_SIZE
    body = f"""      <p class="section-note">Every link found during the crawl, with the status of
      its destination where known.</p>
      <div class="scroll-x"><table class="grid">
        <tr><th>Source page</th><th>Links to</th><th>Type</th><th>Anchor text</th>
        <th>Status</th></tr>
        {table_rows or '<tr><td colspan="5">No links recorded.</td></tr>'}
      </table></div>
      <div class="pager">
        <span>Showing {offset + 1:,}–{offset + len(rows):,}</span>
        <span>
          <a class="{"off" if page <= 1 else ""}"
             href="/crawl/{session_id}/links?page={page - 1}">Previous</a>
          <a class="{"off" if not has_next else ""}"
             href="/crawl/{session_id}/links?page={page + 1}">Next</a>
        </span>
      </div>
      <div class="exports">
        <a class="btn" href="/crawl/{session_id}/export/links">Export all links</a>
        <a class="btn" href="/crawl/{session_id}/export/broken-links">Export broken links</a>
      </div>"""

    return _shell(
        title=f"Links — {session.root_url}",
        page_title="Links",
        crumb="Crawl results",
        subtitle=escape(session.root_url),
        body=body,
        active=f"/crawl/{session_id}/links",
        session_id=session_id,
    )


def technical_page(
    store: CrawlStore, session_id: int, robots_info: Dict[str, Any], sitemap_info: Dict[str, Any]
) -> str:
    session = store.get_session(session_id)

    robots_rows = "".join(
        f'<li><span class="fk">{escape(label)}</span>'
        f'<span class="fv">{escape(str(value))}</span></li>'
        for label, value in (
            ("robots.txt", robots_info.get("url", "—")),
            ("Found", "Yes" if robots_info.get("found") else "No"),
            ("Status", robots_info.get("status") or "—"),
            ("Summary", robots_info.get("summary", "—")),
            ("Crawl-delay", robots_info.get("crawl_delay") or "not set"),
        )
    )

    rules = robots_info.get("rules") or []
    rule_list = "".join(f"<li>{escape(rule)}</li>" for rule in rules) or "<li>No rules</li>"

    sitemaps = robots_info.get("sitemaps") or []
    sitemap_links = "".join(
        f'<li><span class="fv">{escape(url)}</span></li>' for url in sitemaps
    ) or "<li>None declared in robots.txt</li>"

    sitemap_rows = "".join(
        f'<li><span class="fk">{escape(label)}</span>'
        f'<span class="fv">{escape(str(value))}</span></li>'
        for label, value in (
            ("Sitemaps found", len(sitemap_info.get("found") or [])),
            ("URLs listed", sitemap_info.get("url_count", 0)),
            ("Is an index", "Yes" if sitemap_info.get("is_index") else "No"),
            ("Duplicate entries", sitemap_info.get("duplicate_count", 0)),
        )
    )

    in_sitemap = store.count_urls(session_id, "in_sitemap = 1")
    not_in_sitemap = store.count_urls(
        session_id, "in_sitemap = 0 AND status_code >= 200 AND status_code < 300"
    )

    body = f"""      <div class="grid-2">
        <div class="card card-pad">
          <div class="card-head"><h3 class="card-title">robots.txt</h3></div>
          <ul class="factlist">{robots_rows}</ul>
          <p class="card-note" style="margin-top:14px"><b>Rules applied to this crawler</b></p>
          <ul class="notes">{rule_list}</ul>
          <p class="card-note"><b>Sitemaps declared</b></p>
          <ul class="factlist">{sitemap_links}</ul>
        </div>
        <div class="card card-pad">
          <div class="card-head"><h3 class="card-title">Sitemap</h3></div>
          <ul class="factlist">{sitemap_rows}</ul>
          <p class="card-note" style="margin-top:14px"><b>Coverage</b></p>
          <ul class="factlist">
            <li><span class="fk">Crawled and in the sitemap</span>
                <span class="fv">{in_sitemap:,}</span></li>
            <li><span class="fk">Crawled but missing from it</span>
                <span class="fv">{not_in_sitemap:,}</span></li>
          </ul>
          <div class="exports">
            <a class="btn" href="/crawl/{session_id}/urls?filter=not-in-sitemap">
              See pages missing from the sitemap</a>
          </div>
        </div>
      </div>"""

    return _shell(
        title=f"Robots and sitemap — {session.root_url}",
        page_title="Robots & Sitemap",
        crumb="Crawl results",
        subtitle=escape(session.root_url),
        body=body,
        active=f"/crawl/{session_id}/technical",
        session_id=session_id,
    )
