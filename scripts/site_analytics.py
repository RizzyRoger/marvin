#!/usr/bin/env python3
"""Private localhost analytics for marvin.sarl (page views + Stripe revenue).

Binds to 127.0.0.1 only. Never expose this process to the public internet.

Setup:
  1. Create a free GoatCounter site with code matching docs/config.js
     (default: marvinsarl) → https://www.goatcounter.com
  2. Export STRIPE_SECRET_KEY (Dashboard → Developers → API keys)
  3. Optional: GOATCOUNTER_API_KEY + GOATCOUNTER_CODE for live view counts
  4. Run:  python3 scripts/site_analytics.py
  5. Open: http://127.0.0.1:8765/

Env:
  STRIPE_SECRET_KEY   required for revenue
  STRIPE_PRICE_ID     default: price_1U6xl33iz2XKJx20PAgCIdsv ($5 Marvin)
  GOATCOUNTER_CODE    default: marvinsarl
  GOATCOUNTER_API_KEY optional (Settings → API in GoatCounter)
  ANALYTICS_PORT      default: 8765
"""

from __future__ import annotations

import html
import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PRICE_ID = "price_1U6xl33iz2XKJx20PAgCIdsv"
DEFAULT_GOAT = "marvinsarl"


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _http_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    method: str = "GET",
) -> dict | list:
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body) if body else {}


def fetch_stripe_revenue(secret: str, price_id: str) -> dict:
    """Sum paid Checkout Sessions / PaymentIntents for the $5 Marvin price."""
    base = "https://api.stripe.com/v1"
    ctx = ssl.create_default_context()
    headers = {"Authorization": f"Bearer {secret}"}

    def _get(path_qs: str) -> dict:
        req = urllib.request.Request(f"{base}/{path_qs}")
        for k, v in headers.items():
            req.add_header(k, v)
        with urllib.request.urlopen(req, context=ctx, timeout=45) as resp:
            return json.loads(resp.read().decode("utf-8"))

    payload = _get(
        "payment_intents?"
        + urllib.parse.urlencode({"limit": "100", "expand[]": "data.latest_charge"})
    )
    sessions = _get(
        "checkout/sessions?"
        + urllib.parse.urlencode({"limit": "100", "status": "complete"})
    )

    payments: list[dict] = []
    total_cents = 0
    seen: set[str] = set()

    for s in sessions.get("data") or []:
        if s.get("payment_status") != "paid":
            continue
        amount = int(s.get("amount_total") or 0)
        if amount != 500:
            continue
        sid = s.get("id") or ""
        if not sid or sid in seen:
            continue
        seen.add(sid)
        total_cents += amount
        payments.append(
            {
                "id": sid,
                "amount_cents": amount,
                "currency": (s.get("currency") or "usd").upper(),
                "created": s.get("created"),
                "customer_email": (s.get("customer_details") or {}).get("email")
                or s.get("customer_email"),
                "source": "checkout_session",
            }
        )

    for pi in payload.get("data") or []:
        if pi.get("status") != "succeeded":
            continue
        amount = int(pi.get("amount_received") or pi.get("amount") or 0)
        if amount != 500:
            continue
        pid = pi.get("id") or ""
        if not pid or pid in seen:
            continue
        seen.add(pid)
        total_cents += amount
        payments.append(
            {
                "id": pid,
                "amount_cents": amount,
                "currency": (pi.get("currency") or "usd").upper(),
                "created": pi.get("created"),
                "customer_email": None,
                "source": "payment_intent",
            }
        )

    payments.sort(key=lambda p: p.get("created") or 0, reverse=True)
    return {
        "total_cents": total_cents,
        "total_usd": total_cents / 100.0,
        "count": len(payments),
        "payments": payments[:50],
        "price_id": price_id,
        "error": None,
    }


def fetch_goatcounter_totals(code: str, api_key: str) -> dict:
    """Hit GoatCounter API for hit totals (optional)."""
    if not api_key:
        return {
            "configured": False,
            "total": None,
            "by_path": [],
            "dashboard_url": f"https://{code}.goatcounter.com/",
            "error": None,
        }
    # API: https://www.goatcounter.com/help/api
    url = f"https://{code}.goatcounter.com/api/v0/stats/total"
    try:
        data = _http_json(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        # Also paths
        paths_url = f"https://{code}.goatcounter.com/api/v0/stats/hits?limit=20"
        hits = _http_json(
            paths_url,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        by_path = []
        for row in hits.get("hits") or []:
            by_path.append(
                {
                    "path": row.get("path") or row.get("name") or "?",
                    "count": row.get("count") or row.get("stats") or 0,
                }
            )
        total = data.get("total") or data.get("stats") or data
        if isinstance(total, dict):
            total = total.get("total") or total.get("count")
        return {
            "configured": True,
            "total": total,
            "by_path": by_path,
            "dashboard_url": f"https://{code}.goatcounter.com/",
            "error": None,
            "raw": data,
        }
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:400]
        return {
            "configured": True,
            "total": None,
            "by_path": [],
            "dashboard_url": f"https://{code}.goatcounter.com/",
            "error": f"HTTP {e.code}: {body}",
        }
    except Exception as e:  # noqa: BLE001
        return {
            "configured": True,
            "total": None,
            "by_path": [],
            "dashboard_url": f"https://{code}.goatcounter.com/",
            "error": str(e),
        }


def render_dashboard(views: dict, money: dict, goat_code: str) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    money_err = money.get("error")
    views_err = views.get("error")

    path_rows = ""
    for row in views.get("by_path") or []:
        path_rows += (
            f"<tr><td>{html.escape(str(row['path']))}</td>"
            f"<td class='num'>{html.escape(str(row['count']))}</td></tr>"
        )
    if not path_rows and views.get("configured"):
        path_rows = "<tr><td colspan='2'>No path breakdown yet (or API shape differs).</td></tr>"
    elif not path_rows:
        path_rows = (
            "<tr><td colspan='2'>Set GOATCOUNTER_API_KEY for path breakdown, "
            "or open the GoatCounter dashboard link.</td></tr>"
        )

    pay_rows = ""
    for p in money.get("payments") or []:
        ts = p.get("created")
        when = (
            datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
            if ts
            else "—"
        )
        amt = f"${(p['amount_cents'] / 100):.2f} {p['currency']}"
        email = html.escape(p.get("customer_email") or "—")
        pay_rows += (
            f"<tr><td>{html.escape(when)}</td>"
            f"<td class='num'>{html.escape(amt)}</td>"
            f"<td>{email}</td>"
            f"<td><code>{html.escape(p['id'])}</code></td></tr>"
        )
    if not pay_rows:
        pay_rows = "<tr><td colspan='4'>No $5 payments recorded yet.</td></tr>"

    total_views = views.get("total")
    views_metric = (
        html.escape(str(total_views))
        if total_views is not None
        else "See GoatCounter →"
    )
    revenue = f"${money.get('total_usd', 0):.2f}"
    count = money.get("count", 0)
    dash = html.escape(views.get("dashboard_url") or f"https://{goat_code}.goatcounter.com/")

    err_block = ""
    if money_err:
        err_block += f"<p class='err'>Stripe: {html.escape(str(money_err))}</p>"
    if views_err:
        err_block += f"<p class='err'>GoatCounter: {html.escape(str(views_err))}</p>"
    if not _env("STRIPE_SECRET_KEY"):
        err_block += (
            "<p class='err'>Set STRIPE_SECRET_KEY to load revenue "
            "(Dashboard → Developers → API keys).</p>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="robots" content="noindex,nofollow" />
  <title>Marvin site analytics (private)</title>
  <style>
    :root {{
      --bg: #f6f2e8;
      --card: #e8dfca;
      --text: #292c28;
      --muted: #62665f;
      --highlight: #b8ddbb;
      --border: #b8b09a;
      --err: #8b4a4a;
      --font: "SF Pro Text", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: var(--font);
      background: var(--bg);
      color: var(--text);
      padding: 2rem clamp(1rem, 4vw, 3rem);
      line-height: 1.45;
    }}
    h1 {{ font-size: 1.75rem; margin: 0 0 0.35rem; }}
    .sub {{ color: var(--muted); margin: 0 0 1.75rem; font-size: 0.9rem; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 1rem;
      margin-bottom: 2rem;
    }}
    .metric {{
      background: var(--card);
      border: 1px solid color-mix(in srgb, var(--border) 50%, transparent);
      border-radius: 12px;
      padding: 1.1rem 1.2rem;
    }}
    .metric .label {{ font-size: 0.8rem; color: var(--muted); }}
    .metric .value {{ font-size: 1.85rem; font-weight: 650; margin-top: 0.25rem; }}
    section {{
      margin-bottom: 2rem;
    }}
    h2 {{ font-size: 1.1rem; margin: 0 0 0.75rem; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.9rem;
      background: #fffdf8;
      border-radius: 12px;
      overflow: hidden;
      border: 1px solid color-mix(in srgb, var(--border) 45%, transparent);
    }}
    th, td {{
      text-align: left;
      padding: 0.65rem 0.85rem;
      border-bottom: 1px solid color-mix(in srgb, var(--border) 35%, transparent);
    }}
    th {{ background: var(--card); font-weight: 600; }}
    td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    tr:last-child td {{ border-bottom: none; }}
    a {{ color: #3d5c42; }}
    .err {{ color: var(--err); background: #f3e4e4; padding: 0.65rem 0.85rem; border-radius: 8px; }}
    .note {{
      font-size: 0.85rem;
      color: var(--muted);
      max-width: 42rem;
    }}
    code {{ font-size: 0.8rem; }}
    .badge {{
      display: inline-block;
      background: var(--highlight);
      padding: 0.15rem 0.5rem;
      border-radius: 999px;
      font-size: 0.75rem;
      font-weight: 600;
    }}
  </style>
</head>
<body>
  <p class="badge">localhost only · not public</p>
  <h1>Marvin site analytics</h1>
  <p class="sub">Refreshed {html.escape(now)} · <a href="/">reload</a></p>
  {err_block}
  <div class="grid">
    <div class="metric">
      <div class="label">Page views</div>
      <div class="value">{views_metric}</div>
    </div>
    <div class="metric">
      <div class="label">Revenue ($5 payments)</div>
      <div class="value">{html.escape(revenue)}</div>
    </div>
    <div class="metric">
      <div class="label">Paid checkouts</div>
      <div class="value">{count}</div>
    </div>
  </div>

  <section>
    <h2>Page views</h2>
    <p class="note">
      Privacy counter: <a href="{dash}" target="_blank" rel="noopener">GoatCounter dashboard</a>
      (login required). Site code: <code>{html.escape(goat_code)}</code>.
    </p>
    <table>
      <thead><tr><th>Path</th><th class="num">Hits</th></tr></thead>
      <tbody>{path_rows}</tbody>
    </table>
  </section>

  <section>
    <h2>Payments</h2>
    <p class="note">
      One-time $5 Payment Link checkouts (price
      <code>{html.escape(money.get("price_id") or DEFAULT_PRICE_ID)}</code>).
    </p>
    <table>
      <thead>
        <tr>
          <th>When (UTC)</th>
          <th class="num">Amount</th>
          <th>Email</th>
          <th>Id</th>
        </tr>
      </thead>
      <tbody>{pay_rows}</tbody>
    </table>
  </section>

  <p class="note">
    This server listens on 127.0.0.1 only. Do not tunnel or deploy it.
    Public site tracking is GoatCounter only — no analytics cookies on marvin.sarl.
  </p>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:  # quieter
        sys_stderr = __import__("sys").stderr
        sys_stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def do_GET(self) -> None:  # noqa: N802
        if self.path not in ("/", "/index.html", "/dashboard"):
            self.send_error(404)
            return
        goat = _env("GOATCOUNTER_CODE", DEFAULT_GOAT)
        secret = _env("STRIPE_SECRET_KEY")
        price = _env("STRIPE_PRICE_ID", DEFAULT_PRICE_ID)
        api_key = _env("GOATCOUNTER_API_KEY")

        views = fetch_goatcounter_totals(goat, api_key)
        if secret:
            try:
                money = fetch_stripe_revenue(secret, price)
            except Exception as e:  # noqa: BLE001
                money = {
                    "total_cents": 0,
                    "total_usd": 0.0,
                    "count": 0,
                    "payments": [],
                    "price_id": price,
                    "error": str(e),
                }
        else:
            money = {
                "total_cents": 0,
                "total_usd": 0.0,
                "count": 0,
                "payments": [],
                "price_id": price,
                "error": None,
            }

        body = render_dashboard(views, money, goat).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    port = int(_env("ANALYTICS_PORT", "8765") or "8765")
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Private analytics: http://127.0.0.1:{port}/")
    print("Ctrl+C to stop. Bound to localhost only.")
    if not _env("STRIPE_SECRET_KEY"):
        print("Warning: STRIPE_SECRET_KEY unset — revenue section empty.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
