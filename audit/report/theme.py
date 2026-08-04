"""Shared visual language for the report and the web UI.

Kept in one place so the served pages and a saved report file cannot drift apart. Everything
here is inlined at render time — no external stylesheet, font, or icon request is ever made.
"""

from __future__ import annotations

# Inline stroke icons, 24x24 viewBox, drawn in currentColor. Paths only, so they can be
# dropped into a sized <svg> wrapper wherever they are needed.
ICON_PATHS = {
    "dashboard": "M3 3h7v7H3zM14 3h7v4h-7zM14 10h7v11h-7zM3 13h7v8H3z",
    "search": "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM20 20l-4-4",
    "heading": "M6 4v16M18 4v16M6 12h12",
    "tag": "M3 12V5a2 2 0 0 1 2-2h7l9 9-9 9z M7.5 7.5h.01",
    "link": "M10 13a5 5 0 0 0 7 0l2-2a5 5 0 0 0-7-7l-1 1M14 11a5 5 0 0 0-7 0l-2 2a5 5 0 0 0 7 7l1-1",
    "image": "M3 5h18v14H3zM3 16l5-5 4 4 3-3 6 6",
    "weight": "M12 3a3 3 0 0 0-3 3h6a3 3 0 0 0-3-3zM5 6h14l2 15H3z",
    "eye": "M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7zM12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z",
    "code": "M9 6l-6 6 6 6M15 6l6 6-6 6",
    "layers": "M12 3l9 5-9 5-9-5zM3 14l9 5 9-5",
    "alert": "M12 4l9 16H3zM12 10v4M12 17h.01",
    "wand": "M4 20L16 8M14 4l1 3 3 1-3 1-1 3-1-3-3-1 3-1zM19 13l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7z",
    "gauge": "M12 21a9 9 0 1 1 9-9M12 12l5-3",
    "arrow": "M7 17L17 7M9 7h8v8",
    "check": "M20 6L9 17l-5-5",
    "back": "M19 12H5M12 19l-7-7 7-7",
}


def icon(name: str, size: int = 18, extra_class: str = "") -> str:
    """Inline SVG for a named icon."""
    path = ICON_PATHS.get(name, ICON_PATHS["dashboard"])
    classes = f' class="{extra_class}"' if extra_class else ""
    return (
        f'<svg{classes} width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        f'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" '
        f'stroke-linejoin="round" aria-hidden="true"><path d="{path}"/></svg>'
    )


BRAND_MARK = (
    '<svg width="30" height="30" viewBox="0 0 32 32" fill="none" aria-hidden="true">'
    '<rect width="32" height="32" rx="9" fill="currentColor"/>'
    '<path d="M10 16.5l4 4 8-8.5" stroke="#fff" stroke-width="2.4" stroke-linecap="round" '
    'stroke-linejoin="round"/></svg>'
)


# The whole design system. Split out of the renderers so both the report and the web UI
# forms share exactly one source of truth for colour, radius, and spacing.
BASE_CSS = """
*, *::before, *::after { box-sizing: border-box; }

:root {
  color-scheme: light dark;

  --accent:        #0f7a52;
  --accent-hover:  #0c6544;
  --accent-ink:    #ffffff;
  --accent-soft:   #e6f4ee;
  --accent-line:   #bfe3d3;

  --bg:            #f4f6f5;
  --surface:       #ffffff;
  --surface-2:     #fafbfa;
  --border:        #e5e8e7;
  --border-strong: #d4d9d7;

  --ink:           #0f1a16;
  --ink-2:         #5b6b64;
  --ink-3:         #93a09a;

  --critical: #a8231b;
  --high:     #cf3a2c;
  --medium:   #c47510;
  --low:      #0d7490;
  --info:     #6b7b74;
  --good:     #12805c;
  --warn:     #d98218;
  --bad:      #d64535;

  --r-xl: 20px;
  --r-lg: 16px;
  --r-md: 11px;
  --r-sm: 8px;

  --shadow-sm: 0 1px 2px rgba(15,26,22,.05);
  --shadow-md: 0 1px 3px rgba(15,26,22,.06), 0 6px 16px -8px rgba(15,26,22,.12);

  --sidebar-w: 260px;
}

@media (prefers-color-scheme: dark) {
  :root {
    --accent:        #2ea87a;
    --accent-hover:  #37bb89;
    --accent-ink:    #06221a;
    --accent-soft:   #12352a;
    --accent-line:   #1d4e3c;

    --bg:            #0b0f0e;
    --surface:       #141a18;
    --surface-2:     #191f1d;
    --border:        #242c29;
    --border-strong: #313b37;

    --ink:           #eef2f0;
    --ink-2:         #9aa8a2;
    --ink-3:         #6b7a74;

    --critical: #fda29b;
    --high:     #f58b7f;
    --medium:   #f0b054;
    --low:      #67d8e8;
    --info:     #9aa8a2;
    --good:     #34d399;
    --warn:     #f0b054;
    --bad:      #f58b7f;

    --shadow-sm: none;
    --shadow-md: none;
  }
}

html { -webkit-text-size-adjust: 100%; }

body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font: 15px/1.6 ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
        "Helvetica Neue", Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

a { color: var(--accent); }

code, .mono, pre {
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
}

/* ---------------------------------------------------------------- app shell */

.app { position: relative; display: grid; grid-template-columns: var(--sidebar-w) minmax(0,1fr);
       min-height: 100vh; }
.app > input[type=radio] {
  position: absolute; width: 1px; height: 1px; margin: -1px; padding: 0;
  overflow: hidden; white-space: nowrap; clip: rect(0 0 0 0); clip-path: inset(50%); border: 0;
}

.sidebar { position: sticky; top: 0; align-self: start; height: 100vh; display: flex;
           flex-direction: column; gap: 6px; padding: 22px 14px; background: var(--surface);
           border-right: 1px solid var(--border); overflow-y: auto; }

.brand { display: flex; align-items: center; gap: 11px; padding: 4px 10px 20px; }
.brand-mark { color: var(--accent); display: flex; }
.brand-name { font-size: 16px; font-weight: 680; letter-spacing: -.015em; line-height: 1.15; }
.brand-sub { font-size: 11px; color: var(--ink-3); font-weight: 500; }

.navgroup { margin: 16px 10px 7px; font-size: 10.5px; font-weight: 700; letter-spacing: .1em;
            text-transform: uppercase; color: var(--ink-3); }

.navitem { display: flex; align-items: center; gap: 11px; padding: 9px 11px; border-radius: var(--r-md);
           font-size: 14px; font-weight: 520; color: var(--ink-2); cursor: pointer;
           user-select: none; text-decoration: none; line-height: 1.3; }
.navitem:hover { background: var(--surface-2); color: var(--ink); }
.navitem svg { flex: 0 0 auto; opacity: .85; }
.navitem .navlabel { flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis;
                     white-space: nowrap; }
.navitem .pill { flex: 0 0 auto; min-width: 21px; text-align: center; padding: 1px 7px;
                 border-radius: 999px; font-size: 11px; font-weight: 650;
                 background: var(--surface-2); border: 1px solid var(--border); color: var(--ink-2); }
.navitem .pill.hot { background: var(--bad); border-color: var(--bad); color: #fff; }
@media (prefers-color-scheme: dark) { .navitem .pill.hot { color: #14100f; } }

.sidefoot { margin-top: auto; padding-top: 18px; }
.sidecard { background: linear-gradient(155deg, var(--accent) 0%, var(--accent-hover) 100%);
            color: var(--accent-ink); border-radius: var(--r-lg); padding: 17px 16px; }
.sidecard h4 { margin: 0 0 5px; font-size: 13.5px; font-weight: 660; }
.sidecard p { margin: 0; font-size: 12px; opacity: .88; line-height: 1.55; }
.sidecard code { display: block; margin-top: 11px; padding: 7px 9px; border-radius: var(--r-sm);
                 background: rgba(255,255,255,.16); font-size: 11.5px; word-break: break-all; }

/* ---------------------------------------------------------------- main */

.main { min-width: 0; display: flex; flex-direction: column; }

.topbar { display: flex; flex-wrap: wrap; gap: 16px; align-items: center;
          padding: 20px 30px; border-bottom: 1px solid var(--border);
          background: var(--surface); }
.topbar-main { flex: 1 1 320px; min-width: 0; }
.crumb { font-size: 11px; font-weight: 650; letter-spacing: .09em; text-transform: uppercase;
         color: var(--ink-3); margin: 0 0 5px; }
.topbar h1 { margin: 0; font-size: 20px; font-weight: 680; letter-spacing: -.02em;
             line-height: 1.25; word-break: break-word; }
.topbar .sub { margin: 4px 0 0; font-size: 13px; color: var(--ink-2); word-break: break-all; }
.topbar .sub a { text-decoration: none; }
.topbar .sub a:hover { text-decoration: underline; }
.topbar-side { display: flex; gap: 9px; align-items: center; flex: 0 0 auto; }

.btn { display: inline-flex; align-items: center; gap: 7px; padding: 9px 15px;
       border-radius: 999px; font-size: 13.5px; font-weight: 600; text-decoration: none;
       border: 1px solid var(--border-strong); color: var(--ink); background: var(--surface);
       cursor: pointer; }
.btn:hover { background: var(--surface-2); }
.btn.primary { background: var(--accent); border-color: var(--accent); color: var(--accent-ink); }
.btn.primary:hover { background: var(--accent-hover); border-color: var(--accent-hover); }

.content { padding: 26px 30px 60px; }

/* ---------------------------------------------------------------- cards */

.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-lg);
        box-shadow: var(--shadow-sm); }
.card-pad { padding: 20px 22px; }
.card-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px;
             flex-wrap: wrap; margin-bottom: 15px; }
.card-title { font-size: 14.5px; font-weight: 650; margin: 0; letter-spacing: -.01em; }
.card-note { font-size: 12.5px; color: var(--ink-2); margin: 0; }

.grid-4 { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 14px; }
.grid-2 { display: grid; grid-template-columns: minmax(0,1.55fr) minmax(0,1fr); gap: 14px;
          margin-top: 14px; align-items: start; }
@media (max-width: 1080px) { .grid-2 { grid-template-columns: minmax(0,1fr); } }

/* stat cards */
.stat { position: relative; padding: 18px 20px 17px; border-radius: var(--r-lg);
        background: var(--surface); border: 1px solid var(--border); box-shadow: var(--shadow-sm); }
.stat .k { font-size: 12.5px; font-weight: 600; color: var(--ink-2); margin: 0 0 12px;
           padding-right: 34px; }
.stat .v { font-size: 33px; font-weight: 700; letter-spacing: -.035em; line-height: 1;
           margin: 0 0 9px; font-variant-numeric: tabular-nums; }
.stat .d { font-size: 11.5px; color: var(--ink-3); margin: 0; display: flex; align-items: center;
           gap: 6px; }
.stat .corner { position: absolute; top: 15px; right: 15px; width: 27px; height: 27px;
                border-radius: 50%; display: flex; align-items: center; justify-content: center;
                border: 1px solid var(--border); color: var(--ink-2); }
.stat.accent { background: var(--accent); border-color: var(--accent); color: var(--accent-ink); }
.stat.accent .k, .stat.accent .d { color: var(--accent-ink); opacity: .9; }
.stat.accent .corner { border-color: rgba(255,255,255,.35); color: var(--accent-ink); }
.stat .tone { display: inline-flex; align-items: center; gap: 5px; padding: 2px 8px;
              border-radius: 999px; font-weight: 620; background: var(--surface-2);
              border: 1px solid var(--border); }
.stat.accent .tone { background: rgba(255,255,255,.17); border-color: transparent; }

/* score ring */
.ring { position: relative; width: 132px; height: 132px; flex: 0 0 auto; margin: 0 auto; }
.ring svg { transform: rotate(-90deg); }
.ring-track { stroke: var(--border); }
.ring-val { stroke-linecap: round; }
.ring-text { position: absolute; inset: 0; display: flex; flex-direction: column;
             align-items: center; justify-content: center; }
.ring-num { font-size: 33px; font-weight: 700; letter-spacing: -.03em; line-height: 1;
            font-variant-numeric: tabular-nums; }
.ring-of { font-size: 10px; color: var(--ink-3); text-transform: uppercase;
           letter-spacing: .09em; margin-top: 6px; font-weight: 600; }

/* horizontal meters */
.meters { display: flex; flex-direction: column; gap: 15px; }
.meter-row .mt { display: flex; justify-content: space-between; align-items: baseline;
                 gap: 10px; margin-bottom: 7px; font-size: 13px; }
.meter-row .mt b { font-weight: 660; font-variant-numeric: tabular-nums; }
.meter-row .mt span { color: var(--ink-2); }
.meter { height: 7px; border-radius: 999px; background: var(--border); overflow: hidden; }
.meter i { display: block; height: 100%; border-radius: 999px; }

/* severity legend */
.legend { display: flex; flex-direction: column; gap: 10px; }
.legend-row { display: flex; align-items: center; gap: 10px; font-size: 13px; }
.legend-dot { width: 9px; height: 9px; border-radius: 50%; flex: 0 0 auto; }
.legend-row .lbl { flex: 1 1 auto; color: var(--ink-2); }
.legend-row .num { font-weight: 660; font-variant-numeric: tabular-nums; }

.factlist { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
.factlist li { display: flex; justify-content: space-between; gap: 14px; padding: 9px 0;
               border-bottom: 1px solid var(--border); font-size: 13px; }
.factlist li:last-child { border-bottom: none; }
.factlist .fk { color: var(--ink-2); flex: 0 0 auto; }
.factlist .fv { font-weight: 600; text-align: right; word-break: break-all; min-width: 0; }

/* ---------------------------------------------------------------- panels */

.panel { display: none; }
.panel > section { margin: 0 0 20px; }
.panel > section:last-child { margin-bottom: 0; }

section > h2 { display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
               font-size: 16px; font-weight: 670; margin: 0 0 4px; letter-spacing: -.015em; }
.count-pill { font-size: 11.5px; font-weight: 620; color: var(--ink-2); background: var(--surface);
              border: 1px solid var(--border); padding: 2px 9px; border-radius: 999px; }
.section-note { margin: 0 0 16px; font-size: 13px; color: var(--ink-2); max-width: 78ch; }

/* findings */
.finding { background: var(--surface); border: 1px solid var(--border);
           border-left: 3px solid var(--border); border-radius: var(--r-md);
           padding: 15px 18px; margin-bottom: 10px; box-shadow: var(--shadow-sm); }
.finding.critical { border-left-color: var(--critical); }
.finding.high     { border-left-color: var(--high); }
.finding.medium   { border-left-color: var(--medium); }
.finding.low      { border-left-color: var(--low); }
.finding.info     { border-left-color: var(--info); }
.f-top { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.badge { font-size: 9.5px; font-weight: 700; letter-spacing: .07em; text-transform: uppercase;
         padding: 3px 8px; border-radius: 5px; flex: 0 0 auto; color: #fff; }
.badge.critical { background: var(--critical); }
.badge.high     { background: var(--high); }
.badge.medium   { background: var(--medium); }
.badge.low      { background: var(--low); }
.badge.info     { background: var(--info); }
@media (prefers-color-scheme: dark) { .badge { color: #0b0f0e; } }
.f-title { font-weight: 620; font-size: 14px; flex: 1 1 240px; min-width: 0; word-break: break-word; }
.f-rule { font-size: 11.5px; color: var(--ink-3); }
.f-detail { margin: 8px 0 0; font-size: 13px; color: var(--ink-2); word-break: break-word; }
.f-el { margin: 9px 0 0; padding: 9px 11px; background: var(--surface-2); border: 1px solid var(--border);
        border-radius: var(--r-sm); font-size: 12px; color: var(--ink-2); overflow-x: auto;
        white-space: pre-wrap; word-break: break-all; }
.f-fix { margin: 10px 0 0; padding-left: 12px; border-left: 2px solid var(--accent-line);
         font-size: 13px; color: var(--ink-2); }
.f-fix b { color: var(--ink); font-weight: 640; }

.clean { background: var(--accent-soft); border: 1px solid var(--accent-line);
         border-radius: var(--r-md); padding: 16px 18px; font-size: 13.5px; color: var(--ink-2); }
.clean b { color: var(--good); }

/* blocks list (headings) */
.blocks { border: 1px solid var(--border); border-radius: var(--r-md); overflow: hidden;
          background: var(--border); display: flex; flex-direction: column; gap: 1px; }
.block { display: flex; gap: 13px; padding: 11px 15px; background: var(--surface); align-items: baseline; }
.block .tag { font-size: 10.5px; font-weight: 700; text-transform: uppercase; flex: 0 0 26px;
              color: var(--ink-3); font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
.block.h1 .tag, .block.h2 .tag, .block.h3 .tag { color: var(--accent); }
.block .txt { flex: 1 1 auto; min-width: 0; font-size: 13.5px; word-break: break-word; }
.block.h1 .txt { font-weight: 650; font-size: 15px; }
.block.h2 .txt { font-weight: 620; }
.block.h3 .txt { font-weight: 580; }
.block.p .txt { color: var(--ink-2); }
.block .ln { flex: 0 0 auto; font-size: 11px; color: var(--ink-3);
             font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }

/* structure tree */
.tree { background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-md);
        padding: 15px 17px; overflow-x: auto; font-size: 12.5px; line-height: 1.75;
        font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
.tree div { white-space: pre; }
.tree .t { color: var(--accent); }
.tree .q { color: var(--ink-2); }
.tree .n { color: var(--ink-3); }

/* tables */
.scroll-x { overflow-x: auto; border-radius: var(--r-md); border: 1px solid var(--border); }
table.grid { width: 100%; border-collapse: collapse; background: var(--surface); font-size: 13px; }
table.grid th { text-align: left; font-size: 10.5px; text-transform: uppercase; letter-spacing: .07em;
                color: var(--ink-3); font-weight: 660; padding: 10px 15px;
                border-bottom: 1px solid var(--border); background: var(--surface-2);
                white-space: nowrap; }
table.grid td { padding: 10px 15px; border-bottom: 1px solid var(--border); vertical-align: top;
                word-break: break-all; }
table.grid tr:last-child td { border-bottom: none; }
table.grid td.mono { font-size: 12px; }
.state { display: inline-block; font-size: 9.5px; font-weight: 700; text-transform: uppercase;
         letter-spacing: .05em; padding: 3px 8px; border-radius: 5px; white-space: nowrap; color: #fff; }
.state.missing { background: var(--high); }
.state.empty { background: var(--medium); }
@media (prefers-color-scheme: dark) { .state { color: #0b0f0e; } }

pre.code { background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-md);
           padding: 15px 17px; overflow-x: auto; font-size: 12.5px; line-height: 1.6;
           color: var(--ink); margin: 0; }
.notes { margin: 0 0 15px; padding-left: 18px; font-size: 13px; color: var(--ink-2); }
.notes li { margin-bottom: 5px; }
.chiprow { display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 15px; }
.chip { display: inline-flex; align-items: baseline; gap: 7px; padding: 5px 12px; border-radius: 999px;
        border: 1px solid var(--border); background: var(--surface); font-size: 12.5px; color: var(--ink-2); }
.chip b { font-size: 13px; font-weight: 660; color: var(--ink); }

footer.foot { margin-top: 34px; padding-top: 18px; border-top: 1px solid var(--border);
              font-size: 12px; color: var(--ink-3); line-height: 1.75; max-width: 90ch; }

/* ---------------------------------------------------------------- responsive */

@media (max-width: 900px) {
  .app { grid-template-columns: minmax(0,1fr); }
  .sidebar { position: static; height: auto; flex-direction: row; flex-wrap: nowrap;
             overflow-x: auto; align-items: center; gap: 4px; padding: 11px 13px;
             border-right: none; border-bottom: 1px solid var(--border); }
  .brand, .navgroup, .sidefoot { display: none; }
  .navitem { flex: 0 0 auto; padding: 8px 12px; }
  .navitem .navlabel { max-width: none; }
  .topbar, .content { padding-left: 18px; padding-right: 18px; }
}

@media print {
  .sidebar, .topbar-side { display: none; }
  .app { display: block; }
  .panel { display: block !important; }
  .card, .stat, .finding { box-shadow: none; break-inside: avoid; }
  body { background: #fff; }
}
"""
