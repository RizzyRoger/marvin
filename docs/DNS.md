# Namecheap DNS for marvin.sarl

Point the domain at GitHub Pages.

## Steps

1. Log in to [Namecheap](https://www.namecheap.com/)
2. **Domain List** → `marvin.sarl` → **Manage**
3. Open **Advanced DNS**
4. Delete any existing **URL Redirect**, **Parking**, or conflicting **A** / **CNAME** records for `@` and `www`
5. Add these records:

| Type  | Host | Value                 | TTL    |
|-------|------|-----------------------|--------|
| A     | `@`  | `185.199.108.153`     | Automatic |
| A     | `@`  | `185.199.109.153`     | Automatic |
| A     | `@`  | `185.199.110.153`     | Automatic |
| A     | `@`  | `185.199.111.153`     | Automatic |
| CNAME | `www`| `RizzyRoger.github.io`| Automatic |

6. Save changes
7. Wait for propagation (often 5–60 minutes)
8. In GitHub **Settings → Pages**, confirm custom domain `marvin.sarl`, then turn on **Enforce HTTPS**

## Checks

```bash
dig marvin.sarl +short
dig www.marvin.sarl +short
```

Apex should resolve to the GitHub A addresses above. `www` should CNAME to `RizzyRoger.github.io`.

Then open:

- https://marvin.sarl
- https://www.marvin.sarl
