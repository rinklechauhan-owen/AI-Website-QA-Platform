"""robots.txt fetching and evaluation.

`urllib.robotparser` exists in the standard library, but it answers only "may I fetch this?".
The brief requires showing *why* a URL was blocked and which directive did it, so rules are
parsed here and the matching rule is returned alongside the verdict.

Matching follows the de-facto standard the major crawlers implement: the longest matching
path pattern wins, and `Allow` beats `Disallow` when both patterns are the same length.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit

from audit.fetch import DEFAULT_TIMEOUT, DEFAULT_USER_AGENT, FetchError, fetch


@dataclass
class Rule:
    allow: bool
    pattern: str
    regex: "re.Pattern[str]"

    @property
    def specificity(self) -> int:
        # Wildcards are not literal characters, so they do not add specificity.
        return len(self.pattern.replace("*", "").replace("$", ""))

    def __str__(self) -> str:
        return f"{'Allow' if self.allow else 'Disallow'}: {self.pattern}"


@dataclass
class RobotsTxt:
    url: str
    found: bool = False
    status: Optional[int] = None
    body: str = ""
    error: Optional[str] = None
    sitemaps: List[str] = field(default_factory=list)
    crawl_delay: Optional[float] = None
    # Rules that applied to our user agent, in file order.
    rules: List[Rule] = field(default_factory=list)
    matched_group: Optional[str] = None

    @property
    def blocks_everything(self) -> bool:
        return any(r.pattern == "/" and not r.allow for r in self.rules)

    def decision(self, url: str) -> Tuple[bool, Optional[Rule]]:
        """(allowed, deciding rule). A missing or unreadable robots.txt allows everything."""
        if not self.found or not self.rules:
            return True, None

        parts = urlsplit(url)
        path = urlunsplit(("", "", parts.path or "/", parts.query, ""))

        best: Optional[Rule] = None
        for rule in self.rules:
            if not rule.regex.match(path):
                continue
            if best is None:
                best = rule
                continue
            if rule.specificity > best.specificity:
                best = rule
            elif rule.specificity == best.specificity and rule.allow and not best.allow:
                # Equal specificity: the permissive rule wins.
                best = rule

        if best is None:
            return True, None
        return best.allow, best

    def allows(self, url: str) -> bool:
        return self.decision(url)[0]

    def explain(self, url: str) -> str:
        allowed, rule = self.decision(url)
        if rule is None:
            return "Allowed — no matching robots.txt rule"
        return f"{'Allowed' if allowed else 'Blocked'} by `{rule}`"

    def summary(self) -> str:
        if self.error:
            return f"Could not be read ({self.error}) — crawling everything"
        if not self.found:
            return f"Not found (HTTP {self.status}) — crawling everything"
        return f"Found — {len(self.rules)} rule(s) for this crawler, {len(self.sitemaps)} sitemap(s)"


def _pattern_to_regex(pattern: str) -> "re.Pattern[str]":
    """robots.txt patterns support `*` for any run of characters and `$` for end-of-URL."""
    anchored_end = pattern.endswith("$")
    if anchored_end:
        pattern = pattern[:-1]

    parts = [re.escape(piece) for piece in pattern.split("*")]
    body = ".*".join(parts)
    return re.compile("^" + body + ("$" if anchored_end else ""))


def parse(text: str, user_agent: str = DEFAULT_USER_AGENT) -> Tuple[List[Rule], List[str], Optional[float], Optional[str]]:
    """Return (rules for this agent, sitemaps, crawl delay, matched group name).

    Sitemap directives are global — they are collected regardless of which group they sit in.
    """
    agent_token = user_agent.split("/")[0].strip().lower()

    groups: List[Tuple[List[str], List[Rule], Optional[float]]] = []
    sitemaps: List[str] = []

    current_agents: List[str] = []
    current_rules: List[Rule] = []
    current_delay: Optional[float] = None
    expecting_agents = False

    def flush() -> None:
        if current_agents:
            groups.append((list(current_agents), list(current_rules), current_delay))

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue

        field_name, _, value = line.partition(":")
        field_name = field_name.strip().lower()
        value = value.strip()

        if field_name == "user-agent":
            if not expecting_agents:
                flush()
                current_agents, current_rules, current_delay = [], [], None
                expecting_agents = True
            current_agents.append(value.lower())
            continue

        expecting_agents = False

        if field_name in ("allow", "disallow"):
            if not value and field_name == "disallow":
                continue  # "Disallow:" with no value means allow everything.
            if value:
                current_rules.append(
                    Rule(allow=field_name == "allow", pattern=value, regex=_pattern_to_regex(value))
                )
        elif field_name == "crawl-delay":
            try:
                current_delay = float(value)
            except ValueError:
                pass
        elif field_name == "sitemap":
            if value:
                sitemaps.append(value)

    flush()

    # Prefer a group naming this crawler; fall back to the wildcard group.
    for agents, rules, delay in groups:
        for agent in agents:
            if agent and agent != "*" and (agent in agent_token or agent_token.startswith(agent)):
                return rules, sitemaps, delay, agent

    for agents, rules, delay in groups:
        if "*" in agents:
            return rules, sitemaps, delay, "*"

    return [], sitemaps, None, None


def robots_url_for(site_url: str) -> str:
    parts = urlsplit(site_url)
    return urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))


def load(
    site_url: str,
    user_agent: str = DEFAULT_USER_AGENT,
    timeout: int = DEFAULT_TIMEOUT,
    verify_tls: bool = True,
) -> RobotsTxt:
    """Fetch and parse robots.txt. Never raises — an unreadable file means "crawl freely"."""
    url = robots_url_for(site_url)
    result = RobotsTxt(url=url)

    try:
        response = fetch(url, timeout=timeout, user_agent=user_agent, verify_tls=verify_tls)
    except FetchError as exc:
        result.error = str(exc)
        return result

    result.status = response.status
    if response.status >= 400:
        return result

    result.found = True
    result.body = response.body
    rules, sitemaps, delay, group = parse(response.body, user_agent)
    result.rules = rules
    result.sitemaps = sitemaps
    result.crawl_delay = delay
    result.matched_group = group
    return result
