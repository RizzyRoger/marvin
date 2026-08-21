# Publishing marvin.sarl (GitHub Pages)

This folder is the static landing page for **https://marvin.sarl**.

## Enable Pages

1. Open the repo on GitHub: [RizzyRoger/marvin](https://github.com/RizzyRoger/marvin)
2. **Settings → Pages**
3. **Build and deployment → Source:** Deploy from a branch
4. **Branch:** `main` (or your default), folder **`/docs`**
5. Save
6. Under **Custom domain**, enter `marvin.sarl` and save
7. After DNS works, enable **Enforce HTTPS**

`docs/CNAME` already contains `marvin.sarl` so GitHub keeps the custom domain on deploy.

## Local preview

```bash
cd docs
python3 -m http.server 8080
```

Open http://127.0.0.1:8080

## DNS

See [DNS.md](DNS.md) for the exact Namecheap records.

## Analytics (private)

Page views use **GoatCounter** (privacy-friendly, no cookies). Revenue is **not** shown on the public site.

1. Create a free site at [goatcounter.com](https://www.goatcounter.com) with code **`marvinsarl`** (must match `goatCounterCode` in `config.js`).
2. For a combined private dashboard on your Mac:

```bash
export STRIPE_SECRET_KEY='sk_live_…'   # or sk_test_…
# optional, for path totals in the local UI:
# export GOATCOUNTER_API_KEY='…'
python3 scripts/site_analytics.py
```

Open http://127.0.0.1:8765/ — bound to localhost only.
