"""GHOST bug-bounty skill pack.

7 skills designed for AUTHORIZED testing only:
  - scope_confirm   (gate before any active probe)
  - passive_recon   (zero traffic to target: crt.sh, DNS, WHOIS)
  - tech_fingerprint (one HTTP GET)
  - security_headers (one HTTP GET, scores missing headers)
  - misconfig_sweep  (checks ~40 well-known paths, rate-limited, gated)
  - port_scan        (top-100 TCP, gated)
  - draft_report     (produces a HackerOne-style markdown report)

Every active skill gates on confirm() in the terminal. Logged to ghost.log.
"""
from __future__ import annotations

import json
import socket
import ssl
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests

# Re-import confirm from sibling module at runtime to avoid circular import.
def _confirm(prompt: str) -> bool:
    from skills import confirm
    return confirm(prompt)


# ---------- Scope gate ----------
def scope_confirm(target: str, program: str = "") -> dict:
    """Ask the user to confirm the target is in an authorised bug-bounty scope.

    GHOST refuses to run any active scan unless this has been called and
    answered 'yes' for that target in the current session.
    """
    msg = (f"Confirm: '{target}' is IN SCOPE for the bug-bounty program "
           f"'{program or '<not specified>'}', and you are AUTHORISED to test it?")
    ok = _confirm(msg)
    if not ok:
        return {"approved": False, "target": target, "message": "User did not confirm scope. No active scans will run."}
    _SCOPE_APPROVED.add(target.lower().strip())
    return {"approved": True, "target": target, "program": program or None}


_SCOPE_APPROVED: set[str] = set()


def _require_scope(target: str) -> dict | None:
    """Return an error dict if target isn't pre-approved; else None."""
    if target.lower().strip() not in _SCOPE_APPROVED:
        return {
            "error": "scope_not_confirmed",
            "message": f"Call scope_confirm('{target}', program='<name>') first. "
                       "GHOST will not run active probes against unconfirmed targets.",
        }
    return None


# ---------- Passive recon (zero packets to target) ----------
def passive_recon(domain: str) -> dict:
    domain = (domain or "").strip().lower()
    if not domain:
        return {"error": "no domain"}

    result: dict[str, Any] = {"domain": domain}

    # 1. Subdomain enum via crt.sh (public certificate transparency, third-party)
    try:
        r = requests.get(f"https://crt.sh/?q=%25.{domain}&output=json", timeout=20,
                         headers={"User-Agent": "GhostBugBounty/1.0"})
        if r.ok:
            seen = set()
            for entry in r.json():
                for name in (entry.get("name_value") or "").split("\n"):
                    name = name.strip().lower()
                    if name and "*" not in name and name.endswith(domain):
                        seen.add(name)
            result["subdomains"] = sorted(seen)[:200]
            result["subdomain_count"] = len(seen)
    except Exception as e:
        result["subdomains_error"] = str(e)

    # 2. DNS records (uses local resolver, not a packet to target)
    try:
        import dns.resolver  # type: ignore
        records = {}
        for rtype in ("A", "AAAA", "MX", "NS", "TXT", "CNAME"):
            try:
                ans = dns.resolver.resolve(domain, rtype, lifetime=5)
                records[rtype] = [r.to_text() for r in ans]
            except Exception:
                pass
        result["dns"] = records
    except ImportError:
        # fall back to socket.gethostbyname_ex
        try:
            host, aliases, ips = socket.gethostbyname_ex(domain)
            result["dns"] = {"A": ips, "aliases": aliases}
        except Exception as e:
            result["dns_error"] = str(e)

    return result


# ---------- Tech fingerprint (1 HTTP GET) ----------
def tech_fingerprint(url: str) -> dict:
    target = _normalize_url(url)
    try:
        r = requests.get(target, timeout=15, allow_redirects=True,
                         headers={"User-Agent": "Mozilla/5.0 GhostBugBounty/1.0"})
    except Exception as e:
        return {"error": str(e), "url": target}

    hints: list[str] = []
    h = {k.lower(): v for k, v in r.headers.items()}
    body = r.text[:200_000].lower()

    fingerprints = {
        "WordPress": ["wp-content", "wp-includes", "/wp-json/"],
        "Drupal": ["drupal-settings-json", "sites/default/files"],
        "Joomla": ["joomla!", "/components/com_"],
        "Django": ["csrfmiddlewaretoken", "djangoproject"],
        "Laravel": ["laravel_session", "x-powered-by: php"],
        "Rails": ["x-runtime", "rack-cache"],
        "Next.js": ["__next", "/_next/"],
        "React": ["__react_devtools", "react-root"],
        "Vue.js": ["data-v-", "__vue__"],
        "Angular": ["ng-version=", "ng-app="],
        "Cloudflare": ["server: cloudflare", "__cfduid", "cf-ray"],
        "AWS CloudFront": ["x-amz-cf-id", "x-cache: hit from cloudfront"],
        "Nginx": ["server: nginx"],
        "Apache": ["server: apache"],
        "IIS": ["server: microsoft-iis"],
        "Express": ["x-powered-by: express"],
    }
    headers_blob = "\n".join(f"{k}: {v}" for k, v in h.items())
    for tech, sigs in fingerprints.items():
        for s in sigs:
            if s in body or s in headers_blob.lower():
                hints.append(tech)
                break

    return {
        "url": target,
        "status": r.status_code,
        "server": h.get("server"),
        "x_powered_by": h.get("x-powered-by"),
        "tech_hints": sorted(set(hints)),
        "title": _extract_title(r.text),
        "content_type": h.get("content-type"),
    }


def _extract_title(html: str) -> str | None:
    import re
    m = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    return m.group(1).strip()[:200] if m else None


def _normalize_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


# ---------- Security headers ----------
def security_headers(url: str) -> dict:
    target = _normalize_url(url)
    try:
        r = requests.get(target, timeout=15, allow_redirects=True,
                         headers={"User-Agent": "GhostBugBounty/1.0"})
    except Exception as e:
        return {"error": str(e)}
    h = {k.lower(): v for k, v in r.headers.items()}

    checks = {
        "Strict-Transport-Security": h.get("strict-transport-security"),
        "Content-Security-Policy": h.get("content-security-policy"),
        "X-Frame-Options": h.get("x-frame-options"),
        "X-Content-Type-Options": h.get("x-content-type-options"),
        "Referrer-Policy": h.get("referrer-policy"),
        "Permissions-Policy": h.get("permissions-policy"),
        "Cross-Origin-Opener-Policy": h.get("cross-origin-opener-policy"),
    }
    missing = [k for k, v in checks.items() if not v]
    score = round(100 * (len(checks) - len(missing)) / len(checks))
    return {
        "url": target,
        "status": r.status_code,
        "score_out_of_100": score,
        "missing": missing,
        "present": {k: v for k, v in checks.items() if v},
        "exposes_server_version": bool(h.get("server") and any(c.isdigit() for c in h["server"])),
    }


# ---------- Misconfig sweep ----------
COMMON_MISCONFIG_PATHS = [
    "/.git/HEAD", "/.git/config", "/.env", "/.env.local", "/.env.production",
    "/.DS_Store", "/.svn/entries", "/.htaccess", "/.htpasswd",
    "/backup.zip", "/backup.tar.gz", "/db.sql", "/database.sql",
    "/admin", "/admin/", "/administrator", "/wp-admin/",
    "/phpmyadmin/", "/server-status", "/server-info",
    "/api/", "/api/v1/", "/swagger.json", "/swagger-ui.html",
    "/openapi.json", "/graphql", "/graphiql",
    "/.well-known/security.txt", "/robots.txt", "/sitemap.xml",
    "/config.json", "/config.yml", "/config.php",
    "/wp-config.php.bak", "/.aws/credentials", "/web.config",
    "/composer.json", "/package.json", "/Gemfile",
    "/.vscode/settings.json", "/.idea/workspace.xml",
    "/debug", "/_debug", "/console", "/test.php", "/info.php",
]


def misconfig_sweep(url: str, max_workers: int = 4, delay: float = 0.5) -> dict:
    target = _normalize_url(url).rstrip("/")
    host = urllib.parse.urlparse(target).hostname or ""
    gate = _require_scope(host)
    if gate:
        return gate
    if not _confirm(f"Run misconfig sweep ({len(COMMON_MISCONFIG_PATHS)} requests, ~{int(len(COMMON_MISCONFIG_PATHS)*delay/max_workers)}s) against {target}?"):
        return {"status": "cancelled"}

    findings = []
    sess = requests.Session()
    sess.headers["User-Agent"] = "GhostBugBounty/1.0 (authorized scan)"

    def _probe(path: str) -> dict | None:
        full = target + path
        try:
            r = sess.get(full, timeout=10, allow_redirects=False)
            time.sleep(delay)
            if r.status_code in (200, 401, 403) and len(r.content) > 0:
                preview = r.text[:200].replace("\n", " ")
                return {
                    "path": path, "status": r.status_code,
                    "length": len(r.content), "preview": preview,
                }
        except Exception:
            return None
        return None

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for f in as_completed([ex.submit(_probe, p) for p in COMMON_MISCONFIG_PATHS]):
            res = f.result()
            if res:
                findings.append(res)

    return {
        "target": target,
        "checked": len(COMMON_MISCONFIG_PATHS),
        "interesting": sorted(findings, key=lambda x: x["status"]),
        "tip": "200 = exposed file. 401/403 = exists but protected (still worth a closer look).",
    }


# ---------- Port scan (top 100 TCP, socket-based, no nmap needed) ----------
TOP_100_PORTS = [
    21, 22, 23, 25, 53, 80, 110, 111, 135, 139, 143, 443, 445, 465, 587, 993, 995,
    1080, 1433, 1521, 1723, 2049, 2375, 2376, 2483, 3000, 3001, 3128, 3306, 3389, 3690,
    4000, 4040, 4369, 4443, 4444, 4500, 4567, 4848, 5000, 5001, 5432, 5601, 5672, 5800,
    5900, 5984, 6000, 6379, 6443, 6660, 6667, 7000, 7001, 7077, 7474, 7547, 7777, 7878,
    8000, 8008, 8009, 8010, 8080, 8081, 8086, 8088, 8090, 8091, 8443, 8500, 8530, 8765,
    8834, 8888, 9000, 9001, 9042, 9090, 9091, 9092, 9100, 9200, 9300, 9418, 9999, 10000,
    11211, 15672, 25565, 27017, 27018, 27019, 32400, 50000, 50070, 50075, 54321, 6066, 6553,
]


def port_scan(target: str, timeout: float = 1.0, max_workers: int = 32) -> dict:
    host = target.strip()
    gate = _require_scope(host)
    if gate:
        return gate
    if not _confirm(f"Run TCP port scan (top {len(TOP_100_PORTS)} ports) against {host}?"):
        return {"status": "cancelled"}

    try:
        ip = socket.gethostbyname(host)
    except Exception as e:
        return {"error": f"dns resolution failed: {e}"}

    def _check(port: int) -> int | None:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            r = s.connect_ex((ip, port))
            return port if r == 0 else None
        finally:
            s.close()

    open_ports: list[int] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for f in as_completed([ex.submit(_check, p) for p in TOP_100_PORTS]):
            v = f.result()
            if v:
                open_ports.append(v)

    # banner grab for known service hints
    services = {21: "FTP", 22: "SSH", 25: "SMTP", 53: "DNS", 80: "HTTP",
                110: "POP3", 143: "IMAP", 443: "HTTPS", 445: "SMB",
                3306: "MySQL", 3389: "RDP", 5432: "PostgreSQL",
                6379: "Redis", 8080: "HTTP-alt", 9200: "Elasticsearch",
                27017: "MongoDB", 11211: "Memcached"}
    return {
        "target": host, "ip": ip,
        "open_ports": sorted(open_ports),
        "services_guess": {p: services.get(p, "?") for p in sorted(open_ports)},
    }


# ---------- Report drafting ----------
def draft_report(title: str, target: str, severity: str = "Medium",
                 summary: str = "", steps: str = "", impact: str = "",
                 evidence: str = "") -> dict:
    sev = severity.strip().capitalize()
    cvss_hint = {"Critical": "9.0–10.0", "High": "7.0–8.9", "Medium": "4.0–6.9",
                 "Low": "0.1–3.9", "Informational": "0.0"}.get(sev, "n/a")

    summary_md = summary or "<one-paragraph description of the vulnerability>"
    steps_md = steps or "1. ...\n2. ...\n3. ..."
    impact_md = impact or "<who is affected and how — be specific about data exposed or actions an attacker can take>"
    evidence_md = evidence or "<request/response pairs, screenshots, PoC URL>"

    md = f"""# {title}

**Target:** {target}
**Severity:** {sev} (CVSS {cvss_hint})
**Reporter:** (your handle)
**Date:** {_today()}

## Summary
{summary_md}

## Steps to Reproduce
{steps_md}

## Impact
{impact_md}

## Evidence
{evidence_md}

## Remediation
<your recommendation — e.g. 'add Content-Security-Policy header', 'patch to version X', 'invalidate the leaked tokens'>

## References
- (CVE / CWE links if applicable)
- (vendor docs)
"""
    return {"markdown": md, "char_count": len(md)}


def _today() -> str:
    import datetime as _dt
    return _dt.date.today().isoformat()


# ---------- Tool schemas ----------
BUG_BOUNTY_TOOLS = [
    {
        "name": "scope_confirm",
        "description": "REQUIRED before any active scan. Ask the user to confirm a target is in an authorised bug-bounty scope. The user replies y/N in the terminal. Without a 'yes' here, port_scan and misconfig_sweep will refuse.",
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "hostname or domain, e.g. 'example.com'"},
                "program": {"type": "string", "description": "bug-bounty program name (HackerOne, Bugcrowd, etc.)"},
            },
            "required": ["target"],
        },
    },
    {
        "name": "passive_recon",
        "description": "Zero-traffic-to-target recon. Subdomain enum via crt.sh (public CT logs), DNS records. Safe to run on anything.",
        "input_schema": {
            "type": "object",
            "properties": {"domain": {"type": "string"}},
            "required": ["domain"],
        },
    },
    {
        "name": "tech_fingerprint",
        "description": "Single HTTP GET to identify framework / CMS / web server from headers and body markers.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "security_headers",
        "description": "Single HTTP GET, scores missing security headers (CSP, HSTS, X-Frame-Options, etc.) and returns a 0–100 score.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "misconfig_sweep",
        "description": "Probes ~40 well-known sensitive paths (.git/HEAD, .env, /admin, swagger, etc.) on a target. REQUIRES scope_confirm first and prompts user once more before running. Rate-limited.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "port_scan",
        "description": "TCP scan of top-100 common ports against a single host. REQUIRES scope_confirm first and prompts user once more before running. Pure Python sockets, no nmap.",
        "input_schema": {
            "type": "object",
            "properties": {"target": {"type": "string"}},
            "required": ["target"],
        },
    },
    {
        "name": "draft_report",
        "description": "Generates a HackerOne-style markdown bug-bounty report from the fields the user provides. Returns markdown ready to paste.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "target": {"type": "string"},
                "severity": {"type": "string", "enum": ["Critical", "High", "Medium", "Low", "Informational"]},
                "summary": {"type": "string"},
                "steps": {"type": "string"},
                "impact": {"type": "string"},
                "evidence": {"type": "string"},
            },
            "required": ["title", "target"],
        },
    },
]

BUG_BOUNTY_DISPATCH = {
    "scope_confirm": scope_confirm,
    "passive_recon": passive_recon,
    "tech_fingerprint": tech_fingerprint,
    "security_headers": security_headers,
    "misconfig_sweep": misconfig_sweep,
    "port_scan": port_scan,
    "draft_report": draft_report,
}
