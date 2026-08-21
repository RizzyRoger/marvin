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
