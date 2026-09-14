# StarEastStore — a complete Django e-commerce platform

A production-ready e-commerce website built with **Python 3.12+ / Django 5.2 (LTS)**,
PostgreSQL (SQLite fallback for development), Django REST Framework and a modern
responsive Bootstrap 5 storefront. Every major feature works end-to-end —
register → browse → cart → coupon → checkout → payment → verification → order →
inventory updates → order history.

---

## Features

| Area | What's included |
|---|---|
| **Catalog** | Categories, brands, products, multiple images, flexible size/colour variants with their own SKU/price/stock |
| **Storefront** | Home, shop, category/brand pages, sale page, search, product detail with gallery, related products, reviews |
| **Filtering** | Pagination, search, category/brand/price/availability filters, sorting by price / newest / popularity |
| **Cart** | DB-backed cart for customers, session cart for guests, automatic merge at login, stock-aware quantities |
| **Checkout** | Address selection/creation, shipping methods, coupons, order notes, backend-only price computation |
| **Payments** | Gateway architecture: **Stripe Checkout**, **Razorpay**, **cash on delivery** and a built-in **simulated gateway** for demos. Server-side verification, idempotent completion, webhooks, full transaction records |
| **Coupons** | Percentage/fixed discounts, expiry, minimum order, maximum discount cap, usage limits |
| **Orders** | Status workflow (pending → confirmed → processing → shipped → delivered / cancelled / refunded), item snapshots, audit trail, customer cancellation with stock restoration |
| **Inventory** | Row-level-locked stock reduction (`select_for_update`), low-stock thresholds, restoration on cancel/refund, overselling protection |
| **Reviews** | 1–5 ratings with distribution bars, verified-purchase enforcement, one review per user per product (editable) |
| **Wishlist** | Toggle, dedupe, move-to-cart |
| **Accounts** | Email-based registration/login, custom user model, profiles with image upload, multiple addresses with defaults, password reset/change, login rate limiting |
| **Admin** | Custom admin site with operations dashboard (sales, orders, customers, low-stock alerts, recent orders), inlines, filters, bulk order status actions |
| **API** | DRF endpoints for products/categories/brands (filter+search+ordering), cart, wishlist, orders, reviews, token auth |
| **Email** | Welcome, password reset, order confirmation, payment confirmation, shipped/delivered/cancelled notifications — all configurable via env vars |
| **Security** | CSRF, XSS/SQLi-safe ORM, clickjacking protection, upload validation (extension + magic bytes + size), rate limiting, hardened production settings, `.env` secrets |
| **Testing** | 173 automated tests covering registration, cart, coupons, checkout, payment verification, inventory, permissions, reviews, wishlist, APIs |

## Technology

* Python 3.12+ (3.11 works too) · Django 5.2 LTS · Django REST Framework
* PostgreSQL 16 (production) / SQLite (development fallback)
* Bootstrap 5 + Bootstrap Icons (vendored, no CDN required) · Vanilla JS
* Pillow (images) · python-dotenv (env config) · WhiteNoise (static files)
* Gunicorn + Nginx (deployment) · Docker / docker-compose

---

## Quick start (development)

```bash
# 1. Clone & enter the project
git clone <repo-url> StarEastStore
cd StarEastStore

# 2. Virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Linux/macOS

# 3. Install dependencies
pip install -r requirements.txt

# 4. Environment
cp .env.example .env         # defaults work out of the box (SQLite + console email)

# 5. Database
python manage.py migrate

# 6. Demo data (admin, customer, 32 products with generated images, coupons…)
python manage.py seed_data

# 7. Run
python manage.py runserver
```

Visit:

* Storefront — <http://127.0.0.1:8000/>
* Admin panel — <http://127.0.0.1:8000/admin/> (`admin@stareaststore.com` / `admin12345!` — dev defaults, change them!)
* Demo customer — `demo@stareaststore.com` / `demo12345!` (has sample orders, address, reviews)
* REST API — <http://127.0.0.1:8000/api/products/>

> Demo credentials are printed by `seed_data` and come from `DJANGO_ADMIN_EMAIL` /
> `DJANGO_ADMIN_PASSWORD` / `DEMO_CUSTOMER_EMAIL` / `DEMO_CUSTOMER_PASSWORD`
> environment variables when set. Never reuse them in production.

### Creating your own superuser

```bash
python manage.py createsuperuser    # prompts for email + password
```

### Running the tests

```bash
python manage.py test
```

173 tests cover registration/login, product search & filters, cart operations
and quantity validation, coupon rules, checkout, order creation, inventory
reduction/restoration, payment verification & idempotency, permissions,
reviews and the wishlist.

---

## Project structure

```text
StarEastStore/
├── manage.py
├── requirements.txt
├── .env.example           # every supported environment variable
├── Dockerfile
├── docker-compose.yml     # Django + PostgreSQL + Redis + Nginx
├── gunicorn.conf.py
├── deploy/nginx.conf      # production Nginx reference config
├── ecommerce/             # project package (settings, urls, admin site, wsgi/asgi)
├── accounts/              # custom user, profiles, addresses, auth backend
├── products/              # categories, brands, products, images, variants, search
├── cart/                  # session + database carts, merge service, stock service
├── orders/                # checkout, orders, items, coupons, shipping methods
├── payments/              # gateway abstraction: simulated / Stripe / Razorpay
├── reviews/               # verified-purchase reviews
├── wishlist/              # wishlist with move-to-cart
├── core/                  # home/static pages, contact, emails, utils, seed_data
├── api/                   # DRF serializers, viewsets, routes
├── templates/             # base + per-app templates, emails, admin override
├── static/                # CSS, JS, vendored Bootstrap
├── media/                 # uploads (gitignored, created at runtime)
└── fixtures/              # optional JSON fixtures
```

## The payment flow (section 27 of the spec)

```text
Checkout (address + shipping + coupon + payment method)
   ↓  place_order()  — everything re-validated server-side
Order created (status=pending) + PaymentTransaction (initiated)
   ↓  gateway.initiate()
Simulated gateway page / Stripe Checkout redirect / Razorpay checkout.js
   ↓  user pays
Return URL → server verifies with the gateway (never the browser)
   ↓  verify_and_complete() — idempotent, row-level locking
Payment marked succeeded → order paid + confirmed
   ↓
Stock reduced exactly once (stock_deducted flag guards double deduction)
Coupon usage incremented exactly once
   ↓
Order + payment confirmation emails → order history
```

Failure and cancellation paths keep the order pending (retryable) or cancel
it while restoring stock and flagging refunds.

## Environment variables

See [`.env.example`](.env.example) for the full annotated list. Highlights:

```env
DEBUG=True
SECRET_KEY=change-me
DATABASE_URL=postgresql://user:password@localhost:5432/ecommerce   # omit for SQLite
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
EMAIL_HOST= EMAIL_PORT= EMAIL_HOST_USER= EMAIL_HOST_PASSWORD=
STRIPE_SECRET_KEY= STRIPE_PUBLISHABLE_KEY= STRIPE_WEBHOOK_SECRET=
RAZORPAY_KEY_ID= RAZORPAY_KEY_SECRET= RAZORPAY_WEBHOOK_SECRET=
TAX_RATE=0.00
FREE_SHIPPING_THRESHOLD=75
ALLOWED_HOSTS= CSRF_TRUSTED_ORIGINS=              # required for custom domains
SERVE_MEDIA= AUTO_MIGRATE= AUTO_COLLECTSTATIC=     # defaults suit Render deploys
```

Payment gateways activate automatically when their SDK is installed and keys
are configured; the simulated gateway is enabled in DEBUG mode by default
(`SIMULATED_GATEWAY_ENABLED`).

`ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS` only need the hostnames you serve from
yourself: on Render the platform's own `*.onrender.com` hostname is detected
automatically (`DISABLE_PLATFORM_AUTODETECT=True` opts out).

## Payment configuration

### Stripe
```bash
pip install stripe
# .env
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...          # optional but recommended
```
Checkout uses Stripe Checkout Sessions. The browser return hits
`/payment/verify/<reference>/`, which re-retrieves the session server-side;
webhooks post to `/payment/webhook/stripe/`.

### Razorpay
```bash
pip install razorpay
# .env
RAZORPAY_KEY_ID=rzp_test_...
RAZORPAY_KEY_SECRET=...
```
The checkout page loads Razorpay's checkout.js; the handler posts the payment
identifiers back and the server verifies the HMAC signature before marking
the order paid. Webhooks: `/payment/webhook/razorpay/`.

## API overview

| Endpoint | Methods | Auth |
|---|---|---|
| `/api/products/` · `/api/products/<slug>/` | GET | public (search `?search=`, filters `?category=&brand=&min_price=&max_price=&in_stock=`, ordering `?ordering=`) |
| `/api/categories/` · `/api/brands/` | GET | public |
| `/api/products/<slug>/reviews/` | GET | public |
| `/api/cart/` | GET/POST/PATCH/DELETE | session (guest ok) |
| `/api/wishlist/` | GET/POST/DELETE | required |
| `/api/orders/` · `/api/orders/<number>/` | GET | required (owner only) |
| `/api/reviews/create/` | POST | required (+verified purchase) |
| `/api/auth/token/` | POST | credentials → DRF token |

## Production deployment

### Docker (recommended)

```bash
cp .env.example .env      # fill in real values, DEBUG=False
docker compose up -d --build
docker compose exec web python manage.py createsuperuser
```

That runs Django under Gunicorn behind Nginx with PostgreSQL and Redis.

### Bare metal

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # DEBUG=False, real SECRET_KEY, DATABASE_URL...
python manage.py migrate
python manage.py collectstatic
python manage.py createsuperuser
gunicorn ecommerce.wsgi:application --config gunicorn.conf.py
```

Then serve with the provided `deploy/nginx.conf` (static/media + reverse
proxy) and TLS via certbot. Key production settings (all env-driven):
`SECURE_SSL_REDIRECT`, `SECURE_COOKIES`, `SECURE_HSTS`, `BEHIND_PROXY`,
`STATIC_MANIFEST=True` (hashed, compressed static files).

### Render

The repository ships a [Render Blueprint](https://render.com/docs/blueprint-spec)
(`render.yaml`) that creates the Django web service **and** its PostgreSQL
database:

1. Push this repository to GitHub (or GitLab/Bitbucket).
2. In the Render Dashboard: **New → Blueprint Instance**, pick the repository,
   click **Apply**. Render builds with `build.sh`, applies migrations, collects
   static files and starts Gunicorn.
3. Create the first admin account from the Render **Shell**:
   `python manage.py createsuperuser`.
4. Optional demo data (their own accounts, 32 products, coupons):
   `python manage.py seed_data`.

Your service is reachable at `https://<service-name>.onrender.com` - the
hostname follows the service name, so keep it as `stareaststore` if you want
`stareaststore.onrender.com`.

**Environment variables.** The only ones required are `SECRET_KEY` (use
*Generate*) and `DATABASE_URL` (the blueprint wires it up automatically from the
database it creates). `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` do **not** have
to be set: on startup the app reads the service's own hostname from Render's
`RENDER_EXTERNAL_HOSTNAME` environment variable and allows it. Add entries there
only for **custom domains**, e.g.

```dotenv
ALLOWED_HOSTS=stareaststore.onrender.com,example.com,www.example.com
CSRF_TRUSTED_ORIGINS=https://example.com,https://www.example.com
```

Existing service deployed by hand? Set the Build Command to `./build.sh`, the
Start Command to
`gunicorn ecommerce.wsgi:application --config gunicorn.conf.py`, the Health
Check Path to `/health/` and add the `SECRET_KEY` / `DATABASE_URL` (plus
`DEBUG=False`) environment variables, then trigger a deploy.

Two useful notes for Render's free plan: web services spin down after ~15
minutes of inactivity (the next request is slow), and free PostgreSQL databases
expire 30 days after creation. Gunicorn binds `$PORT` automatically, and on
Render `DEBUG` defaults to `False` and `SECURE_SSL_REDIRECT`/`BEHIND_PROXY` to
`True`.

**Uploaded files.** Render's native runtime has no web server in front of the
app, so `/media/` uploads (product images, avatars) are served by Django itself
(`SERVE_MEDIA`, on by default there). They are stored on the instance's disk,
which Render replaces on every deploy - attach a [persistent disk](https://render.com/docs/disks)
mounted at `/app/media` (paid plans) or switch to object storage
(`SERVE_MEDIA=False` + a custom storage backend) if you keep uploads.

### Production checklist

- [ ] `DEBUG=False`, unique `SECRET_KEY` from the environment
- [ ] PostgreSQL `DATABASE_URL` with a strong password
- [ ] `ALLOWED_HOSTS` + `CSRF_TRUSTED_ORIGINS` set to your domain (Render's own
      hostname is detected automatically)
- [ ] HTTPS terminated at Nginx/load balancer; `SECURE_SSL_REDIRECT=True`
- [ ] SMTP email backend configured (`EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`)
- [ ] Change/remove the seeded admin & demo users (`python manage.py shell`)
- [ ] `SIMULATED_GATEWAY_ENABLED=False` once real gateways are configured
- [ ] Regular `manage.py migrate` during deploys; database backups scheduled

## Troubleshooting

### Every page returns "400 Bad request" (or looks like a 404) after deploying

Django rejects any request whose `Host` header is not in `ALLOWED_HOSTS` with a
`DisallowedHost` error, which renders the branded **400** page. Because the check
runs before routing, *all* URLs fail at once - the homepage, `/health/`, the
stylesheets under `/static/...` - so the deployment looks like the site (or the
page you requested) does not exist.

It happens when `DEBUG=False` and `ALLOWED_HOSTS` still holds the development
value (`localhost,127.0.0.1`). This project prevents it automatically: the
settings module reads the service's own hostname from Render's
`RENDER_EXTERNAL_HOSTNAME` (also `RENDER_EXTERNAL_URL`) and adds it to
`ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS`. If you are on another host (Railway,
Fly, a VPS...), set them yourself:

```dotenv
ALLOWED_HOSTS=mystore.example.com
CSRF_TRUSTED_ORIGINS=https://mystore.example.com
```

Related symptoms with the same root cause: forms (login, cart, checkout) failing
with **403 CSRF verification failed** - the site's origin is missing from
`CSRF_TRUSTED_ORIGINS`; or payment redirects pointing at `http://` - set
`BEHIND_PROXY=True` when a load balancer terminates TLS.

### Product images 404 under `/media/` after deploying

Django only serves uploads automatically while `DEBUG=True`. On a platform
without a web server in front of the app, set `SERVE_MEDIA=True` (the default on
Render) so Django serves them, or point `MEDIA_URL` at object storage/CDN. Note
that on hosts with an ephemeral filesystem the files themselves are lost on
redeploy - see the Render section above.

### Deployed site loads, but is unstyled and 404s under `/static/`

`collectstatic` did not run during the build. `build.sh` handles this (and
`gunicorn.conf.py` retries it at startup on Render); otherwise run
`python manage.py collectstatic --noinput` in your release step.

### Database errors: "no such table" / "relation does not exist"

Migrations were never applied to the deployed database. `build.sh` runs
`manage.py migrate` and, on Render, Gunicorn re-applies them at startup
(`AUTO_MIGRATE=False` disables that). Attach a PostgreSQL database and set
`DATABASE_URL`: without it the app falls back to SQLite, whose file lives on the
service's ephemeral disk and is wiped on every deploy.

## Management commands

| Command | Purpose |
|---|---|
| `python manage.py seed_data` | Demo catalog, users, coupons, orders (`--force` to re-run) |
| `python manage.py migrate` | Apply migrations |
| `python manage.py test` | Run the test suite |

## License

Provided for demonstration/educational use. Review and harden before running
a real store.
