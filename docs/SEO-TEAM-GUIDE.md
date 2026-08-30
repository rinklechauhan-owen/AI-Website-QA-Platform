# Website QA — Guide for the SEO Team

How to run it, what each screen means, and what it can and cannot tell you.

No account, no login, no installation beyond Python. Nothing you audit is uploaded anywhere —
it runs entirely on your own machine.

---

## Setting up (once)

1. Install Python from [python.org/downloads](https://www.python.org/downloads/). On the first
   screen, tick **"Add python.exe to PATH"** before clicking Install.
2. Download this project as a folder.
3. Open a terminal in that folder and check it works:

```bash
python --version
```

Anything starting `Python 3.9` or higher is fine. There is nothing else to install — no
database, no accounts, no API keys.

---

## Running it

```bash
python -m audit --serve
```

A browser tab opens. Leave the terminal window open while you work; closing it stops the tool.

You will see two choices:

| | When to use it |
| --- | --- |
| **Single Page Audit** | One page, in full detail. Good for checking a page before it goes live, or diagnosing one URL. |
| **Full Website Crawl** | Follows internal links across the whole site, up to 2,000 pages. Good for a site audit, a migration check, or finding duplicates and broken links. |

---

## Running a website crawl

Paste the **home page** URL and press **Start crawl**. The defaults are sensible; the settings
that matter most:

| Setting | Leave it at | Change it when |
| --- | --- | --- |
| **Maximum URLs** | 2000 | A small site — lower it and the crawl finishes sooner |
| **Crawl depth** | Unlimited | You only want the top few levels |
| **Respect robots.txt** | On | Leave this on for client sites |
| **Concurrent requests** | 5 | Lower to 2 if the site is slow or fragile |
| **Delay between requests** | 0 | Raise to 500–1000 ms on a small or shared host |
| **Only crawl URLs containing** | empty | Auditing one section, e.g. `/blog/` |
| **Exclude URLs containing** | empty | Skipping noise, e.g. `/tag/`, `?replytocom=` |
| **Check external links** | On | Turn off to make the crawl faster |
| **Check image sizes** | Off | Turn on to find images over 2.5 MB — slower |

**A note on client sites.** The crawler obeys `robots.txt`, including any `Crawl-delay` the
site asks for, and defaults to five requests at a time. If a site is on shared hosting, set
concurrency to 2 and a delay of 1000 ms. It is better to wait than to be the reason a client's
site slowed down.

While it runs you get a live progress screen with pause, resume and stop. The page refreshes
itself — leave it alone and it will land on the results when the crawl finishes.

---

## Reading the results

### Dashboard

Four numbers at the top: pages crawled, health score (the average page score out of 100),
errors, warnings. Below that: response codes, crawl depth, an at-a-glance list, and every issue
found ordered by severity.

**Click any issue to see only the URLs it affects.** That is the fastest route from "24 pages
are missing meta descriptions" to the list of which 24.

### All URLs

The full table, one row per page — status, title, title length, meta length, H1 count, word
count, internal links, images, missing ALT, depth, issues.

- **Sort** by clicking a column heading.
- **Filter** with the dropdown: 4xx errors, missing titles, missing H1s, non-indexable, images
  missing ALT, not in sitemap, and more.
- **Search** matches URL, title and description.
- Click any URL for its full detail page.

### Issues

Every distinct issue with the number of URLs affected. Click through, then **export that list
to CSV** to hand to a developer.

### Links

Every link found, with the status of its destination. The **Broken links** export gives you
source page, destination and status — which is what a developer needs to fix one.

### Robots & Sitemap

Whether `robots.txt` was found, which rules applied, which sitemaps were declared, how many
URLs they list, and how many crawled pages are missing from the sitemap.

### URL detail

Everything known about one page, plus its issues. The **Run the full single-page audit** button
re-runs the complete audit live for the deepest view of that one page.

---

## Getting results out

**Crawls are not saved.** They live in memory while the tool is open. Close the terminal and
they are gone. This is deliberate — there is no database, nothing stored about the sites you
audit, and nothing to log into.

So **export anything you want to keep**. Every CSV opens directly in Excel:

| Export | Where |
| --- | --- |
| All URLs | Dashboard or All URLs |
| All issues | Dashboard or Issues |
| One issue's URLs | Inside any issue |
| All links | Links |
| Broken links | Dashboard or Links |

---

## What it cannot tell you

Being clear about this matters more than the feature list.

**It reads the HTML the server sends** — the same thing a crawler sees before any JavaScript
runs. It does not run a browser.

On sites built with React, Vue, Angular or similar, the served HTML can be nearly empty. The
tool **detects this and shows an orange banner** on the dashboard saying how many pages are
affected. When you see that banner, treat findings like "missing H1" or "thin content" on those
pages with caution — they may describe what the tool cannot see rather than a real problem.
Confirm anything important with **Google Search Console → URL Inspection**, which shows the
rendered page.

**Not included at all:**

- Page speed and Core Web Vitals (use PageSpeed Insights)
- Full accessibility auditing (use axe or Lighthouse)
- Anything visual — layout, design, screenshots
- Rankings, traffic, backlinks

---

## Command line

Everything above works from a terminal too, which is useful for repeat checks:

```bash
python -m audit https://example.com --crawl --max-urls 500 --out crawl.csv
```

```bash
python -m audit https://example.com/page
```

---

## If something goes wrong

| Symptom | Cause and fix |
| --- | --- |
| `python` not recognised | Python is not on PATH. Reinstall and tick "Add python.exe to PATH". |
| Browser does not open | Go to `http://127.0.0.1:8765` yourself. |
| "Port in use" | It picks the next free port — check the terminal for the address. |
| Crawl finds only one page | The site may block crawlers in `robots.txt`, or links may be JavaScript-generated. Check the Robots & Sitemap screen. |
| Crawl seems slow | Normal at roughly 30 pages a second on a fast site, slower on a slow one. Reduce **Maximum URLs**, or raise concurrency if the site can take it. |
| A page shows as an error but works in a browser | Some hosts block non-browser traffic. Not necessarily a real problem — check manually. |
| Results disappeared | Crawls are not saved. Export to CSV next time. |

**One crawl per person.** The tool runs on your own machine and is only reachable from it. If
several people want to use it, each runs their own copy — do not put it on a shared server, as
it would then fetch any URL anyone asked it to, from your network.
