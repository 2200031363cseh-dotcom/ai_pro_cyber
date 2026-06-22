"""GHOST bug-bounty: extended recon + analysis pack.

12 additional skills for AUTHORISED testing. Same scope-gate model as the
core bug_bounty.py module.
"""
from __future__ import annotations

import base64
import json
import re
import socket
import ssl
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests

from .bug_bounty import _confirm, _require_scope, _normalize_url


# ---------- 1. SSL / TLS analyser ----------
def ssl_analyser(host: str, port: int = 443) -> dict:
    """Pull the cert chain, TLS version, cipher, expiry, SAN list."""
    host = host.strip()
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((host, port), timeout=10) as raw:
            with ctx.wrap_socket(raw, server_hostname=host) as s:
                cert = s.getpeercert()
                cipher = s.cipher()
                tls_version = s.version()
    except Exception as e:
        return {"error": str(e)}

    sans = [v for k, v in (cert.get("subjectAltName") or []) if k == "DNS"]
    issuer = dict(x[0] for x in cert.get("issuer", []))
    subject = dict(x[0] for x in cert.get("subject", []))

    return {
        "host": host, "port": port,
        "tls_version": tls_version,
        "cipher": cipher[0] if cipher else None,
        "cipher_bits": cipher[2] if cipher else None,
        "subject": subject, "issuer": issuer,
        "not_before": cert.get("notBefore"),
        "not_after": cert.get("notAfter"),
        "subject_alt_names": sans[:50],
        "weak_tls": tls_version in ("TLSv1", "TLSv1.1", "SSLv3"),
    }


# ---------- 2. Hash identifier ----------
def hash_id(value: str) -> dict:
    """Guess what kind of hash a string is based on length + charset."""
    v = (value or "").strip()
    hex_only = bool(re.fullmatch(r"[0-9a-fA-F]+", v))
    candidates = []
    length = len(v)
    if hex_only:
        guess = {
            8: ["CRC-32"], 16: ["MySQL323"], 32: ["MD5", "MD4", "NTLM", "LM"],
            40: ["SHA-1", "MySQL5/SHA1"], 56: ["SHA-224"], 64: ["SHA-256", "SHA3-256"],
            96: ["SHA-384"], 128: ["SHA-512", "Whirlpool", "SHA3-512"],
        }.get(length, [])
        candidates.extend(guess)
    if v.startswith("$2a$") or v.startswith("$2b$") or v.startswith("$2y$"):
        candidates.append("bcrypt")
    if v.startswith("$argon2"):
        candidates.append("Argon2")
    if v.startswith("$6$"):
        candidates.append("SHA-512 crypt (Unix)")
    if v.startswith("$5$"):
        candidates.append("SHA-256 crypt (Unix)")
    if v.startswith("$1$"):
        candidates.append("MD5 crypt (Unix)")
    if re.fullmatch(r"[A-Za-z0-9+/=]+", v) and length % 4 == 0:
        candidates.append("(possible base64)")
    if re.fullmatch(r"ey[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]*", v):
        candidates.append("JWT")

    return {"value": v[:64] + ("…" if len(v) > 64 else ""), "length": length, "hex_only": hex_only, "candidates": candidates or ["unknown"]}


# ---------- 3. Decode / encode toolkit ----------
def decode_toolkit(action: str, value: str) -> dict:
    """action: base64_decode | base64_encode | url_decode | url_encode | hex_decode | hex_encode | jwt_decode"""
    try:
        if action == "base64_decode":
            return {"result": base64.b64decode(value + "===").decode("utf-8", errors="replace")}
        if action == "base64_encode":
            return {"result": base64.b64encode(value.encode()).decode()}
        if action == "url_decode":
            return {"result": urllib.parse.unquote(value)}
        if action == "url_encode":
            return {"result": urllib.parse.quote(value)}
        if action == "hex_decode":
            return {"result": bytes.fromhex(value).decode("utf-8", errors="replace")}
        if action == "hex_encode":
            return {"result": value.encode().hex()}
        if action == "jwt_decode":
            parts = value.split(".")
            if len(parts) < 2:
                return {"error": "not a JWT"}
            def _pad(s): return s + "=" * (-len(s) % 4)
            header = json.loads(base64.urlsafe_b64decode(_pad(parts[0])))
            payload = json.loads(base64.urlsafe_b64decode(_pad(parts[1])))
            return {"header": header, "payload": payload, "signature_present": len(parts) == 3 and bool(parts[2])}
        return {"error": f"unknown action: {action}"}
    except Exception as e:
        return {"error": str(e)}


# ---------- 4. HIBP — Have I Been Pwned ----------
def hibp_check(email_or_password: str) -> dict:
    """Check if an email is in known breaches (using public k-anonymity password endpoint
    for passwords; for emails uses a free pwned-domain check via haveibeenpwned breaches API
    which doesn't require a key for the breach-list endpoint)."""
    v = (email_or_password or "").strip()
    if not v:
        return {"error": "empty"}

    # If it looks like an email -> look up unauthenticated breaches by domain
    if "@" in v:
        domain = v.split("@", 1)[1]
        try:
            r = requests.get(
                f"https://haveibeenpwned.com/api/v3/breaches?domain={domain}",
                timeout=15, headers={"User-Agent": "GhostBugBounty/1.0"},
            )
            if r.status_code == 200:
                breaches = [{"name": b["Name"], "date": b.get("BreachDate"),
                             "pwn_count": b.get("PwnCount"), "data_classes": b.get("DataClasses")}
                            for b in r.json()]
                return {"email_domain": domain, "breach_count": len(breaches), "breaches": breaches[:50]}
            return {"status": r.status_code, "note": "HIBP per-account lookup requires an API key. Domain endpoint used."}
        except Exception as e:
            return {"error": str(e)}

    # else treat as password — use k-anonymity range API (no key needed)
    import hashlib
    sha1 = hashlib.sha1(v.encode()).hexdigest().upper()
    prefix, suffix = sha1[:5], sha1[5:]
    try:
        r = requests.get(f"https://api.pwnedpasswords.com/range/{prefix}", timeout=10)
        for line in r.text.splitlines():
            h, count = line.split(":")
            if h == suffix:
                return {"password_pwned": True, "times_seen": int(count)}
        return {"password_pwned": False}
    except Exception as e:
        return {"error": str(e)}


# ---------- 5. CVE lookup via NVD ----------
def cve_lookup(product: str, version: str = "", limit: int = 10) -> dict:
    """Search NIST NVD for CVEs matching a product (and optionally a version)."""
    q = product.strip()
    if version:
        q = f"{product} {version}"
    try:
        r = requests.get(
            "https://services.nvd.nist.gov/rest/json/cves/2.0",
            params={"keywordSearch": q, "resultsPerPage": min(limit, 20)},
            timeout=30, headers={"User-Agent": "Mozilla/5.0 GhostBugBounty/1.0"},
        )
    except requests.exceptions.RequestException as e:
        return {"error": f"network/firewall blocked NVD: {e}"}
    if not r.ok:
        return {"error": f"NVD status {r.status_code}", "body": r.text[:200]}
    try:
        data = r.json()
    except Exception:
        return {"error": "NVD returned non-JSON", "body": r.text[:200]}
    out = []
    for item in data.get("vulnerabilities", []):
        cve = item.get("cve", {})
        metrics = cve.get("metrics", {})
        cvss = None
        for k in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
            if metrics.get(k):
                cvss = metrics[k][0].get("cvssData", {}).get("baseScore")
                break
        descs = cve.get("descriptions") or [{}]
        out.append({
            "id": cve.get("id"),
            "published": cve.get("published"),
            "score": cvss,
            "summary": descs[0].get("value", "")[:240],
        })
    return {"query": q, "results": out, "total": data.get("totalResults", 0)}


# ---------- 6. Wayback URLs ----------
def waybackurls(domain: str, limit: int = 500) -> dict:
    """Pull historical URLs for a domain from the Wayback Machine. Passive."""
    try:
        r = requests.get(
            f"https://web.archive.org/cdx/search/cdx",
            params={"url": f"*.{domain}/*", "output": "json", "fl": "original", "collapse": "urlkey", "limit": limit},
            timeout=30, headers={"User-Agent": "GhostBugBounty/1.0"},
        )
        rows = r.json()
        urls = [row[0] for row in rows[1:]] if rows else []
        # quick interest filter
        interesting = [u for u in urls if any(s in u for s in
            ["?", "/api/", "/admin", "/login", "token=", "key=", "callback=", ".bak", ".old", ".zip", ".sql"])]
        return {"domain": domain, "total": len(urls), "urls": urls[:200], "interesting": interesting[:80]}
    except Exception as e:
        return {"error": str(e)}


# ---------- 7. JS endpoint extractor ----------
_JS_REGEXES = [
    re.compile(r"""[\"']((?:/[A-Za-z0-9_\-./]+)(?:\?[A-Za-z0-9_\-=&%]*)?)[\"']"""),  # absolute paths
    re.compile(r"""[\"'](https?://[^\s\"']+)[\"']"""),                                  # full URLs
    re.compile(r"AKIA[0-9A-Z]{16}"),                                                    # AWS access keys
    re.compile(r"(?i)api[_-]?key[\"'\s:=]+[\"']([A-Za-z0-9_\-]{16,})[\"']"),
    re.compile(r"(?i)bearer\s+([A-Za-z0-9_\-\.=]{20,})"),
]


def js_endpoint_extractor(url: str) -> dict:
    """Fetch a page, follow same-origin .js files, extract endpoints + leaked tokens."""
    target = _normalize_url(url)
    sess = requests.Session()
    sess.headers["User-Agent"] = "GhostBugBounty/1.0"
    try:
        page = sess.get(target, timeout=15)
    except Exception as e:
        return {"error": str(e)}

    base = urllib.parse.urlparse(target)
    js_urls = set()
    for m in re.finditer(r"""<script[^>]+src=[\"']([^\"']+\.js[^\"']*)[\"']""", page.text):
        src = m.group(1)
        if src.startswith("//"):
            src = base.scheme + ":" + src
        elif src.startswith("/"):
            src = f"{base.scheme}://{base.netloc}{src}"
        elif not src.startswith("http"):
            src = urllib.parse.urljoin(target, src)
        if urllib.parse.urlparse(src).netloc == base.netloc:
            js_urls.add(src)

    endpoints: set[str] = set()
    secrets: list[str] = []
    for ju in list(js_urls)[:30]:
        try:
            jr = sess.get(ju, timeout=10)
            for rx in _JS_REGEXES:
                for m in rx.findall(jr.text):
                    val = m if isinstance(m, str) else (m[0] if m else "")
                    if val.startswith("AKIA") or "api" in rx.pattern.lower() or "bearer" in rx.pattern.lower():
                        secrets.append(val[:120])
                    else:
                        endpoints.add(val[:200])
        except Exception:
            continue

    return {
        "page": target,
        "js_files_scanned": len(js_urls),
        "endpoints_found": sorted(endpoints)[:200],
        "potential_secrets": secrets[:30],
    }


# ---------- 8. Subdomain takeover check ----------
TAKEOVER_FINGERPRINTS = {
    "github.io": "There isn't a GitHub Pages site here",
    "herokuapp.com": "no-such-app.herokudns.com",  # CNAME hint
    "amazonaws.com": "NoSuchBucket",
    "azurewebsites.net": "404 Web Site not found",
    "cloudfront.net": "The request could not be satisfied",
    "wordpress.com": "Do you want to register",
    "tumblr.com": "There's nothing here",
    "shopify.com": "Sorry, this shop is currently unavailable",
    "ghost.io": "The thing you were looking for is no longer here",
    "fastly.net": "Fastly error: unknown domain",
    "readme.io": "Project doesnt exist… yet!",
    "zendesk.com": "Help Center Closed",
    "surge.sh": "project not found",
    "pantheonsite.io": "The gods are wise",
}


def subdomain_takeover_check(subdomain: str) -> dict:
    """For one subdomain: resolve CNAME, then fetch HTTP, look for unclaimed-service fingerprints."""
    sub = subdomain.strip().lower()
    cname = None
    try:
        import dns.resolver  # type: ignore
        try:
            ans = dns.resolver.resolve(sub, "CNAME", lifetime=5)
            cname = str(ans[0].target).rstrip(".")
        except Exception:
            cname = None
    except ImportError:
        pass

    body_hits = []
    cname_hits = []
    if cname:
        for service, marker in TAKEOVER_FINGERPRINTS.items():
            if service in cname:
                cname_hits.append(service)
    for scheme in ("https", "http"):
        try:
            r = requests.get(f"{scheme}://{sub}", timeout=8, allow_redirects=True,
                             headers={"User-Agent": "GhostBugBounty/1.0"})
            for service, marker in TAKEOVER_FINGERPRINTS.items():
                if marker.lower() in r.text.lower():
                    body_hits.append({"service": service, "marker": marker, "status": r.status_code})
            break
        except Exception:
            continue

    suspect = bool(cname_hits and (body_hits or True)) or bool(body_hits)
    return {
        "subdomain": sub, "cname": cname,
        "cname_service_hits": cname_hits,
        "body_fingerprint_hits": body_hits,
        "likely_takeover": suspect and bool(body_hits),
        "note": "Even a body hit isn't proof — verify by trying to claim the orphaned service per its docs.",
    }


# ---------- 9. SPF / DKIM / DMARC ----------
def spf_dkim_dmarc(domain: str) -> dict:
    domain = domain.strip().lower()
    out: dict[str, Any] = {"domain": domain}
    try:
        import dns.resolver  # type: ignore
        def _txt(name):
            try:
                ans = dns.resolver.resolve(name, "TXT", lifetime=5)
                return [b"".join(r.strings).decode(errors="replace") for r in ans]
            except Exception:
                return []
        out["spf"] = next((t for t in _txt(domain) if t.lower().startswith("v=spf1")), None)
        dmarc = _txt(f"_dmarc.{domain}")
        out["dmarc"] = next((t for t in dmarc if t.lower().startswith("v=dmarc1")), None)
        out["dkim_default"] = _txt(f"default._domainkey.{domain}")
        out["mx"] = []
        try:
            ans = dns.resolver.resolve(domain, "MX", lifetime=5)
            out["mx"] = [r.to_text() for r in ans]
        except Exception:
            pass
        issues = []
        if not out["spf"]: issues.append("missing SPF")
        elif "+all" in (out["spf"] or "").lower(): issues.append("SPF too permissive (+all)")
        if not out["dmarc"]: issues.append("missing DMARC")
        elif "p=none" in (out["dmarc"] or "").lower(): issues.append("DMARC policy is 'none' (monitoring only)")
        out["issues"] = issues
        return out
    except ImportError:
        return {"error": "dnspython not installed"}


# ---------- 10. GraphQL introspection check ----------
def graphql_introspect(url: str) -> dict:
    """Try a minimal introspection query — useful to flag misconfigured prod APIs."""
    target = _normalize_url(url)
    host = urllib.parse.urlparse(target).hostname or ""
    gate = _require_scope(host)
    if gate:
        return gate
    if not _confirm(f"Send a GraphQL introspection POST to {target}?"):
        return {"status": "cancelled"}

    query = {"query": "query { __schema { types { name } } }"}
    try:
        r = requests.post(target, json=query, timeout=15,
                          headers={"User-Agent": "GhostBugBounty/1.0", "Content-Type": "application/json"})
        try:
            data = r.json()
        except Exception:
            return {"status": r.status_code, "introspection_enabled": False, "body_preview": r.text[:300]}
        if data.get("data", {}).get("__schema"):
            types = [t["name"] for t in data["data"]["__schema"]["types"] if not t["name"].startswith("__")]
            return {"status": r.status_code, "introspection_enabled": True, "type_count": len(types), "sample_types": types[:30]}
        return {"status": r.status_code, "introspection_enabled": False, "errors": data.get("errors")}
    except Exception as e:
        return {"error": str(e)}


# ---------- 11. Directory brute (light, user-provided wordlist) ----------
def directory_brute(url: str, wordlist: list[str] | None = None,
                    extensions: list[str] | None = None,
                    max_workers: int = 4, delay: float = 0.4) -> dict:
    """Probe a small wordlist of paths under a target. Scope-gated + confirmed.

    Defaults to a built-in 50-word list. You can pass your own wordlist (list of
    strings, no slashes) for bigger sweeps.
    """
    default = [
        "admin", "administrator", "login", "logout", "dashboard", "panel", "config",
        "backup", "backups", "old", "test", "tests", "tmp", "temp", "dev", "staging",
        "api", "api/v1", "api/v2", "graphql", "graphiql", "swagger", "docs", "doc",
        "robots", "sitemap", "phpinfo", "info", "status", "health", "metrics",
        "uploads", "files", "downloads", "private", "internal", "console", "debug",
        "users", "user", "accounts", "register", "signup", "reset", "forgot",
        "wp-admin", "wp-login.php", "phpmyadmin", "redmine", "jenkins", "gitlab",
    ]
    words = wordlist or default
    exts = extensions or ["", ".php", ".bak", ".old", ".txt", ".json", ".zip"]
    target = _normalize_url(url).rstrip("/")
    host = urllib.parse.urlparse(target).hostname or ""
    gate = _require_scope(host)
    if gate:
        return gate
    total = len(words) * len(exts)
    if total > 2000:
        return {"error": f"too many requests ({total}). Limit to 2000 max. Slice your wordlist."}
    if not _confirm(f"Run directory brute on {target} — {total} requests (~{int(total*delay/max_workers)}s)?"):
        return {"status": "cancelled"}

    sess = requests.Session()
    sess.headers["User-Agent"] = "GhostBugBounty/1.0 (authorised scan)"
    hits = []

    def _probe(path: str) -> dict | None:
        full = f"{target}/{path}"
        try:
            r = sess.head(full, timeout=8, allow_redirects=False)
            time.sleep(delay)
            if r.status_code in (200, 201, 204, 301, 302, 401, 403):
                return {"path": path, "status": r.status_code, "length": int(r.headers.get("content-length") or 0)}
        except Exception:
            return None
        return None

    paths: list[str] = []
    for w in words:
        for e in exts:
            paths.append(w + e)

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for f in as_completed([ex.submit(_probe, p) for p in paths]):
            res = f.result()
            if res:
                hits.append(res)

    return {"target": target, "probed": len(paths), "hits": sorted(hits, key=lambda x: x["status"])[:200]}


# ---------- 12. Workflow orchestrator ----------
def bug_bounty_workflow(domain: str, program: str = "") -> dict:
    """Chain: scope_confirm -> passive_recon -> tech_fingerprint -> security_headers
    -> spf_dkim_dmarc -> waybackurls. All passive or near-passive."""
    from .bug_bounty import scope_confirm, passive_recon, tech_fingerprint, security_headers

    summary: dict[str, Any] = {"domain": domain, "program": program}
    sc = scope_confirm(domain, program)
    summary["scope"] = sc
    if not sc.get("approved"):
        return summary

    summary["passive_recon"] = passive_recon(domain)
    summary["tech_fingerprint"] = tech_fingerprint(f"https://{domain}")
    summary["security_headers"] = security_headers(f"https://{domain}")
    summary["email_security"] = spf_dkim_dmarc(domain)
    summary["wayback"] = waybackurls(domain, limit=300)

    # Triage: what looks interesting
    leads: list[str] = []
    sh = summary["security_headers"]
    if isinstance(sh, dict) and sh.get("missing"):
        leads.append(f"Missing security headers: {', '.join(sh['missing'])}")
    es = summary["email_security"]
    if isinstance(es, dict) and es.get("issues"):
        leads.extend(es["issues"])
    pr = summary["passive_recon"]
    if isinstance(pr, dict):
        subs = pr.get("subdomains", [])
        if len(subs) > 5:
            leads.append(f"{len(subs)} subdomains found — pick the dev/staging/api ones to dig into next.")
    wb = summary["wayback"]
    if isinstance(wb, dict) and wb.get("interesting"):
        leads.append(f"{len(wb['interesting'])} historical URLs with params/admin/api markers — review for forgotten endpoints.")

    summary["next_steps"] = leads or ["No obvious low-hanging fruit from passive scan. Move to active probing (port_scan / misconfig_sweep / directory_brute) if scope allows."]
    return summary


# ---------- Tool schemas ----------
EXTRA_BB_TOOLS = [
    {"name": "ssl_analyser", "description": "Pull TLS version, cipher suite, cert chain, expiry, and SAN list from an HTTPS host.",
     "input_schema": {"type": "object", "properties": {"host": {"type": "string"}, "port": {"type": "integer"}}, "required": ["host"]}},
    {"name": "hash_id", "description": "Identify likely hash type (MD5, SHA-1, bcrypt, JWT, etc.) from length and charset.",
     "input_schema": {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]}},
    {"name": "decode_toolkit", "description": "Encode/decode utilities. action: base64_decode | base64_encode | url_decode | url_encode | hex_decode | hex_encode | jwt_decode",
     "input_schema": {"type": "object", "properties": {"action": {"type": "string"}, "value": {"type": "string"}}, "required": ["action", "value"]}},
    {"name": "hibp_check", "description": "Have-I-Been-Pwned lookup. Pass an email (returns breaches by domain) or a password (uses k-anonymity range API).",
     "input_schema": {"type": "object", "properties": {"email_or_password": {"type": "string"}}, "required": ["email_or_password"]}},
    {"name": "cve_lookup", "description": "Search NIST NVD for CVEs matching a product (and optional version). Returns ID, score, summary.",
     "input_schema": {"type": "object", "properties": {"product": {"type": "string"}, "version": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["product"]}},
    {"name": "waybackurls", "description": "Pull historical URLs for a domain from the Internet Archive Wayback Machine. Passive (no traffic to target).",
     "input_schema": {"type": "object", "properties": {"domain": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["domain"]}},
    {"name": "js_endpoint_extractor", "description": "Fetch a page, follow same-origin .js files, regex out API endpoints + potential leaked tokens (AWS keys, bearer tokens, API keys).",
     "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}},
    {"name": "subdomain_takeover_check", "description": "Check one subdomain for orphaned-CNAME takeover potential (GitHub Pages, Heroku, S3, Azure, etc.). Verifies but does NOT attempt the takeover.",
     "input_schema": {"type": "object", "properties": {"subdomain": {"type": "string"}}, "required": ["subdomain"]}},
    {"name": "spf_dkim_dmarc", "description": "Email-security posture: pulls SPF, DMARC, default DKIM TXT records and flags issues (missing, +all, p=none).",
     "input_schema": {"type": "object", "properties": {"domain": {"type": "string"}}, "required": ["domain"]}},
    {"name": "graphql_introspect", "description": "Try a __schema introspection query against a GraphQL endpoint. Scope-gated + confirmed.",
     "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}},
    {"name": "directory_brute", "description": "Probe a target with a small wordlist of paths (default ~50 words × ~7 exts). Scope-gated + confirmed + rate-limited (0.4s).",
     "input_schema": {"type": "object", "properties": {"url": {"type": "string"}, "wordlist": {"type": "array", "items": {"type": "string"}}, "extensions": {"type": "array", "items": {"type": "string"}}}, "required": ["url"]}},
    {"name": "bug_bounty_workflow", "description": "ONE-SHOT passive recon: scope_confirm -> subdomains -> tech -> headers -> email security -> wayback URLs -> triaged next-step suggestions. Run this first on every new target.",
     "input_schema": {"type": "object", "properties": {"domain": {"type": "string"}, "program": {"type": "string"}}, "required": ["domain"]}},
]

EXTRA_BB_DISPATCH = {
    "ssl_analyser": ssl_analyser,
    "hash_id": hash_id,
    "decode_toolkit": decode_toolkit,
    "hibp_check": hibp_check,
    "cve_lookup": cve_lookup,
    "waybackurls": waybackurls,
    "js_endpoint_extractor": js_endpoint_extractor,
    "subdomain_takeover_check": subdomain_takeover_check,
    "spf_dkim_dmarc": spf_dkim_dmarc,
    "graphql_introspect": graphql_introspect,
    "directory_brute": directory_brute,
    "bug_bounty_workflow": bug_bounty_workflow,
}
