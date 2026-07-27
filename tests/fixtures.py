"""Shared HTML fixtures and helpers for the test suite."""

from audit.fetch import Response

# Exercises the parser's awkward cases: entity in the title, a heading wrapping a link,
# a skipped heading level, every alt-attribute state, <picture>, and script content that
# looks like markup.
TRICKY = """<!DOCTYPE html>
<html lang="en-GB">
<head>
  <meta charset="utf-8">
  <title>  Acme   Widgets &amp; Gears </title>
  <meta name="description" content="We sell widgets.">
  <meta property="og:title" content="Acme">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="canonical" href="/home">
  <script type="application/ld+json">{"@type":"Organization","name":"Acme"}</script>
  <style>h1 { color: red; }</style>
</head>
<body>
  <h1>Main <em>Heading</em></h1>
  <h2><a href="/products">Products</a></h2>
  <h4>Skipped level</h4>
  <img src="hero.png" alt="Hero banner">
  <img src="/img/a.jpg">
  <img src="b.webp" alt="">
  <img src="c.png" alt="image" loading="lazy" width="10" height="10">
  <picture><source srcset="d.avif" type="image/avif"><img src="d.png" alt="D"></picture>
  <a href="https://external.example.com/x">External</a>
  <a href="#skip">Anchor only</a>
  <a href="/about" rel="nofollow">About us</a>
  <script>var x = "<h1>not a heading</h1>";</script>
  <p>Some body copy here.</p>
</body>
</html>"""

# Should trip nearly every rule.
MESSY = """<!DOCTYPE html>
<html>
<head><title>Hi</title>
<meta name="robots" content="noindex,nofollow">
</head>
<body>
  <h2>Sub</h2>
  <h5>Deep</h5>
  <h2></h2>
  <img src="a.png">
  <img src="b.png" alt="image">
  <img src="c.png" alt="">
  <img src="d.png" alt="%s">
  <img src="a.png">
  <a href="/x">click here</a>
  <a href="http://insecure.example.com/y">read more</a>
</body></html>""" % ("z" * 150)

# Should trip none of them.
CLEAN = """<!DOCTYPE html>
<html lang="en">
<head>
  <title>Acme Widgets - Precision Gears for Industry</title>
  <meta name="description" content="Acme builds precision gears and widgets for industrial
   customers across the UK, with next-day delivery and a five-year warranty as standard.">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta property="og:title" content="Acme Widgets">
  <meta property="og:description" content="Precision gears for industry.">
  <meta property="og:image" content="https://acme.test/og.png">
  <meta name="twitter:card" content="summary_large_image">
  <link rel="canonical" href="https://acme.test/">
  <script type="application/ld+json">{"@context":"https://schema.org","@type":"Organization"}</script>
</head>
<body>
  <h1>Precision gears, built to order</h1>
  <h2>Why Acme</h2>
  <p>%s</p>
  <img src="hero.webp" alt="A machinist inspecting a finished gear" width="1200" height="630">
  <img src="team.webp" alt="The Acme workshop team" width="800" height="600">
  <img src="gear.webp" alt="Close-up of a helical gear" width="400" height="400" loading="lazy">
  <a href="/products">Browse the full product range</a>
</body></html>""" % (
    "Acme has manufactured precision gearing since 1974. " * 12
)

# Actively tries to break out of the generated report.
HOSTILE = """<!DOCTYPE html>
<html>
<head><title>Pwn</title><script>alert(1)</script></head>
<body>
  <h1>x</h1>
  <img src="a.png?"><script>alert('xss')</script>">
  <img src="b.png" alt="&quot;><script>alert('alt-xss')</script>">
  <a href="/z">"><img src=x onerror=alert(1)></a>
</body></html>"""


def response(html: str, url: str = "https://acme.test/", status: int = 200, **kwargs) -> Response:
    """Build a Response without touching the network."""
    return Response(
        url=url,
        status=status,
        body=html,
        headers=kwargs.pop("headers", {"content-type": "text/html; charset=utf-8"}),
        elapsed_ms=kwargs.pop("elapsed_ms", 120),
        byte_size=kwargs.pop("byte_size", len(html)),
    )
