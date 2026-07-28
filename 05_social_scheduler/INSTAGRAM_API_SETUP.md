# Instagram Graph API Setup — One-Time, Manual (Your Login Required)

This can't be done on your behalf — it requires your own Meta/Facebook login at each
step. Meta's UI changes fairly often, so exact button labels below may drift slightly;
the sequence and requirements are accurate as of this session. If a screen doesn't match,
describe or screenshot it and I'll help interpret it.

## Why this avoids Meta's slow App Review process

Meta has two access tiers:
- **Standard Access** — for apps that only serve Instagram accounts the developer
  themselves owns/manages (exactly this case). No App Review needed.
- **Advanced Access** — required only if your app posts to *other people's* Instagram
  accounts. Needs a full App Review submission (screencasts, use-case writeups, can take
  days to weeks).

Since Ascend Lending Partners is only ever posting to its own account, **Standard Access
is sufficient** — this whole setup should take under an hour, not weeks.

## Prerequisites

1. The Instagram account must be a **Professional account** (Business or Creator) —
   Instagram app → Settings → Account type and tools → Switch to professional account,
   if not already done.
2. That Instagram account must be **linked to a Facebook Page** you manage — Instagram
   Settings → Account → Linked accounts (or via the Facebook Page's own Settings →
   Linked accounts).

## Steps

1. Go to **developers.facebook.com** and log in with the Facebook account that manages
   the Page from above.
2. **My Apps → Create App.** Choose the **Business** app type when prompted.
3. In the app dashboard, **Add Product → Instagram** (may appear as "Instagram API with
   Instagram Login," Meta's naming for this has changed a few times).
4. Under the Instagram product's settings, make sure your own Instagram account is added
   as a person with a role on the app (Admin/Developer/Tester) — this is what qualifies
   it for Standard Access without App Review.
5. Generate an access token — either through the app's own Instagram Login flow, or via
   **Graph API Explorer** (developers.facebook.com/tools/explorer): select your app,
   select the Instagram account, and request these permissions:
   - `instagram_business_basic`
   - `instagram_business_content_publish`
6. Exchange the short-lived token for a **long-lived token** (valid ~60 days) — Meta's
   token debugger/exchange endpoint handles this; the Graph API Explorer usually offers
   a "long-lived token" option directly.
7. Find your **Instagram Business Account ID** (a numeric ID, not your @handle) — via
   Graph API Explorer: `GET /me/accounts` to find your Page ID, then
   `GET /{page-id}?fields=instagram_business_account` to get the linked Instagram ID.

## What to hand back

Once you have both values, add them to `.env` yourself (don't paste them in chat, same
as the OpenAI key):
```
INSTAGRAM_ACCESS_TOKEN=<the long-lived token>
INSTAGRAM_BUSINESS_ID=<the numeric Instagram business account id>
```

## The one recurring maintenance item

**Long-lived tokens expire after ~60 days.** This isn't a one-time setup — you (or a
refresh script) need to regenerate the token roughly every 2 months, or `instagram_publish.py`
will start failing with an auth error. Worth calendar-reminding yourself, or I can build
a token-refresh helper once the initial one is working, since Meta's refresh endpoint can
extend a still-valid token before it expires without redoing the whole OAuth flow.

## Still needed after this: image hosting

The Graph API pulls images by public URL, not from your local disk. `PUBLIC_IMAGE_BASE_URL`
in `.env` needs to point at wherever `03_generated_posts/` ends up hosted (S3, Cloudflare
R2, or similar static hosting) — happy to help set this up once the API credentials side
is sorted.
