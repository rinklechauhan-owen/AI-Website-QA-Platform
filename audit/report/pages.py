"""Server-only pages: the URL form and the schema generator.

They share the app shell and design system with the audit report, so the tool reads as one
product rather than a report plus a couple of utility screens.
"""

from __future__ import annotations

from html import escape
from typing import List, Optional, Tuple

from audit import __version__
from audit.report.theme import BASE_CSS, icon, logo_img
from audit.schemagen import SCHEMA_TYPES, GeneratedSchema

# Extra rules for the two standalone pages. Everything else comes from the shared theme.
_PAGE_CSS = """
.formwrap { max-width: 760px; }
.field { margin-bottom: 18px; }
.field > label { display: block; font-size: var(--fs-sm); font-weight: var(--fw-semibold); margin-bottom: 7px; }
.field .help { font-size: var(--fs-sm); color: var(--ink-2); margin: 0 0 9px; }
input[type=url], input[type=text], select, textarea {
  width: 100%; padding: 12px 14px; font-size: var(--fs-base); border-radius: var(--r-md);
  border: 1px solid var(--border-strong); background: var(--surface); color: var(--ink);
  font-family: inherit;
}
textarea { min-height: 250px; resize: vertical; line-height: 1.6;
           font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: var(--fs-sm); }
input:focus, select:focus, textarea:focus { outline: 2px solid var(--accent); outline-offset: 1px;
                                            border-color: var(--accent); }
.opts { display: flex; flex-direction: column; gap: 11px; margin: 16px 0 22px; }
.opt { display: flex; gap: 10px; align-items: flex-start; font-size: var(--fs-sm); color: var(--ink-2); }
.opt input { margin-top: 3px; flex: 0 0 auto; }
.opt b { color: var(--ink); font-weight: var(--fw-semibold); }
.err { margin: 0 0 20px; padding: 13px 16px; border-radius: var(--r-md); font-size: var(--fs-sm);
       background: var(--surface); border: 1px solid var(--bad); color: var(--bad);
       word-break: break-word; }
.err b { display: block; margin-bottom: 3px; }
.two { display: grid; grid-template-columns: minmax(0,1fr) minmax(0,1fr); gap: 14px; }
@media (max-width: 700px) { .two { grid-template-columns: minmax(0,1fr); } }
.examples { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 9px; }
.examples li { font-size: var(--fs-sm); color: var(--ink-2); }
.examples code { display: block; background: var(--surface-2); border: 1px solid var(--border);
                 border-radius: var(--r-sm); padding: 8px 10px; margin-top: 4px;
                 white-space: pre-wrap; font-size: var(--fs-xs); line-height: 1.55; }
"""


def _shell(
    *,
    title: str,
    page_title: str,
    crumb: str,
    subtitle: str,
    body: str,
    active: str,
    actions: str = "",
) -> str:
    """App shell for a standalone page. Sidebar links are real anchors here, not radios."""
    nav = [
        ("/", "Audit a page", "search"),
        ("/crawl", "Crawl a website", "layers"),
        ("/schema", "Schema Generator", "wand"),
    ]
    items = "\n".join(
        f'    <a class="navitem{" active" if href == active else ""}" href="{href}">'
        f'{icon(name)}<span class="navlabel">{escape(label)}</span></a>'
        for href, label, name in nav
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>{BASE_CSS}{_PAGE_CSS}
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
    <p class="navgroup">Tools</p>
{items}
    <div class="sidefoot">
      <div class="sidecard">
        <h4>No dependencies</h4>
        <p>Python standard library only. No install, no database, no API keys.</p>
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


def audit_form(error: Optional[str] = None, url_value: str = "") -> str:
    error_block = f'<p class="err"><b>Could not run that audit</b>{escape(error)}</p>' if error else ""

    from audit.report.crawl_pages import mode_chooser

    body = f"""      <div class="formwrap">
{mode_chooser()}
        {error_block}
        <div class="card card-pad">
          <form method="post" action="/audit">
            <div class="field">
              <label for="url">Website URL</label>
              <input id="url" name="url" type="url" required autofocus
                     placeholder="https://example.com"
                     value="{escape(url_value, quote=True)}">
            </div>
            <div class="opts">
              <label class="opt">
                <input type="checkbox" name="check_images" value="1" checked>
                <span><b>Check image sizes</b> — measures every image to find any over
                2.5&nbsp;MB. One extra request per image.</span>
              </label>
              <label class="opt">
                <input type="checkbox" name="check_links" value="1">
                <span><b>Check every link</b> — verifies each link resolves. Slower, and makes
                extra requests to the target site.</span>
              </label>
            </div>
            <button class="btn primary" type="submit" style="width:100%;justify-content:center">
              Run audit
            </button>
          </form>
        </div>
        <p class="section-note" style="margin-top:18px">Analyses the served HTML. Performance
        metrics, accessibility rules, and visual review need the browser-based modules and are
        not included.</p>
      </div>"""

    return _shell(
        title="Website QA Audit",
        page_title="Audit a page",
        crumb="Website QA",
        subtitle="Audit one page in full, or crawl an entire website.",
        body=body,
        active="/",
    )


def _result_card(result: GeneratedSchema) -> str:
    if not result.ok:
        warnings = "".join(f"<li>{escape(w)}</li>" for w in result.warnings)
        return f"""<div class="card card-pad">
          <div class="card-head"><h3 class="card-title">Nothing generated</h3></div>
          <p class="card-note">Not enough information in the content to build valid markup.
          Nothing was invented to fill the gaps.</p>
          <ul class="notes" style="margin-top:12px">{warnings}</ul>
        </div>"""

    notes = "".join(f"<li>{escape(n)}</li>" for n in result.notes)
    warnings = "".join(f"<li>{escape(w)}</li>" for w in result.warnings)
    note_block = f'<ul class="notes">{notes}{warnings}</ul>' if (notes or warnings) else ""

    return f"""<div class="card card-pad">
          <div class="card-head">
            <h3 class="card-title">Generated markup</h3>
            <p class="card-note">{escape(result.schema_type)}</p>
          </div>
          <div class="chiprow"><span class="chip">type <b>{escape(result.schema_type)}</b></span>
          <span class="chip">fields <b>{len(result.data)}</b></span></div>
          {note_block}
          <pre class="code">{escape(result.script_block)}</pre>
          <p class="card-note" style="margin-top:12px">Paste this into the page's
          <code>&lt;head&gt;</code>. Validate with Google's Rich Results Test before
          publishing.</p>
        </div>"""


_EXAMPLES: List[Tuple[str, str]] = [
    (
        "FAQ",
        "How long does delivery take?\nTwo to three working days across the UK.\n"
        "Can I return an item?\nYes, within 30 days of receipt.",
    ),
    (
        "Product",
        "Name: Northgate Desk Lamp\nPrice: 89.00\nCurrency: GBP\nBrand: Northgate\n"
        "SKU: NG-LAMP-01\nAvailability: InStock",
    ),
    (
        "Local business",
        "Name: Northgate Studio\nStreet: 14 Bridge Street\nCity: Manchester\n"
        "Postcode: M3 3AB\nPhone: +44 161 000 0000",
    ),
    ("Breadcrumbs", "URL: https://example.com\nHome > Services > Branding"),
]


def schema_generator(
    content: str = "",
    schema_type: str = "auto",
    result: Optional[GeneratedSchema] = None,
) -> str:
    options = "\n".join(
        f'                <option value="{escape(key, quote=True)}"'
        f'{" selected" if key == schema_type else ""}>{escape(label)}</option>'
        for key, label in SCHEMA_TYPES
    )

    examples = "\n".join(
        f"<li><b>{escape(label)}</b><code>{escape(sample)}</code></li>"
        for label, sample in _EXAMPLES
    )

    result_block = _result_card(result) if result is not None else ""

    body = f"""      <div class="grid-2" style="margin-top:0">
        <div>
          <div class="card card-pad">
            <form method="post" action="/schema">
              <div class="field">
                <label for="stype">Schema type</label>
                <p class="help">Auto-detect reads the content and picks the closest fit.</p>
                <select id="stype" name="schema_type">
{options}
                </select>
              </div>
              <div class="field">
                <label for="content">Content</label>
                <p class="help">Paste HTML, or plain text using <code>Key: value</code> lines
                for specific fields. Questions ending in "?" become an FAQ; numbered lines
                become a how-to.</p>
                <textarea id="content" name="content" required
                  placeholder="Name: Northgate Desk Lamp&#10;Price: 89.00&#10;Currency: GBP"
                  >{escape(content)}</textarea>
              </div>
              <button class="btn primary" type="submit"
                      style="width:100%;justify-content:center">Generate schema</button>
            </form>
          </div>
          {result_block}
        </div>

        <div class="card card-pad">
          <div class="card-head"><h3 class="card-title">Input examples</h3></div>
          <ul class="examples">{examples}</ul>
          <p class="card-note" style="margin-top:16px">Only fields present in your content are
          written out. Anything that cannot be derived is left out and flagged, because
          structured data that misstates a page is worse than none at all.</p>
        </div>
      </div>"""

    return _shell(
        title="Schema Generator — Website QA",
        page_title="Schema Generator",
        crumb="Tools",
        subtitle="Turn content into schema.org JSON-LD, ready to paste into the page head.",
        body=body,
        active="/schema",
    )
