# Facebook Page Publishing Setup — One-Time, Manual (Your Login Required)

This is a **separate authorization from the Instagram setup** — your Instagram token
cannot be reused here. Instagram's "Instagram API with Instagram Login" and Facebook's
Page posting are two different products with two different token types, even though
both live under the same Meta developer app.

## What you're getting

A **Facebook Page access token** — lets the same script that posts to Instagram also
post the same 5 images + caption to your linked Facebook Page as a multi-photo post
(Facebook's closest equivalent to Instagram's carousel — same images and caption, just
displayed as Facebook's own multi-photo post format rather than a swipeable carousel).

## Steps

1. Go to **developers.facebook.com/tools/explorer** (Graph API Explorer).
2. In the app dropdown at the top, select the **same app** you already created for
   Instagram (no need for a new one).
3. Click **Get Token → Get User Access Token**.
4. In the permissions picker, check:
   - `pages_show_list`
   - `pages_manage_posts`
5. Click **Generate Access Token** — you'll see a Facebook consent screen asking you to
   approve these permissions for your Page. Approve it.
6. **This is the step that's easy to get wrong**: the token in the address/token box
   after step 5 is still your personal **User** token, not a Page token — even though
   it now carries Page permissions. Posting with it directly fails with `(#100) The
   global id ... is not allowed for this call`, because whatever ID you use with a User
   token isn't recognized as a postable target the same way a Page token's own ID is.
   You must explicitly exchange it: call
   `GET /me/accounts?fields=id,name,access_token` **using that user token**. The
   response lists each Page you manage with its real numeric `id` and a **separate**
   `access_token` field — that `access_token` is the actual Page token, and that `id`
   is the actual Page ID to use. Use *both* values from that response, not the ID from
   anywhere else (a Page's URL or About section can show a different-looking "global
   ID" that won't work here — we hit exactly this the first time through: the Page ID
   copied from elsewhere was `61588790741504`, but `/me/accounts` returned the real
   working ID `1172283685977233` for the same Page).
7. **This was wrong the first time through, corrected here**: a Page token derived
   directly from step 6 inherits the short (~1-2 hour) expiry of the short-lived User
   token you started with — it is *not* long-lived by default, whatever some guides
   claim. It expired mid-session on us. The actual fix is one more exchange, done for
   you by `scripts/refresh_facebook_token.py`:
   - Get your app's **App ID** and **App Secret** from
     developers.facebook.com → your app → **Settings → Basic**.
   - Add `FACEBOOK_APP_ID`, `FACEBOOK_APP_SECRET`, and a fresh
     `FACEBOOK_USER_TOKEN` (from steps 3-5 above) to `.env`.
   - Run `python scripts/refresh_facebook_token.py` — it exchanges the short-lived
     User token for a long-lived one first, *then* derives the Page token from that.
     A Page token obtained this way doesn't expire (confirmed via the token debugger:
     `type: PAGE`, `expires_at: 0`). It writes `FACEBOOK_PAGE_ID` and
     `FACEBOOK_PAGE_ACCESS_TOKEN` into `.env` automatically.
   - `FACEBOOK_USER_TOKEN` itself is only needed transiently for this one exchange —
     safe to clear it from `.env` afterward.

## What to hand back

If running `refresh_facebook_token.py` (recommended — see step 7 above), it writes
`.env` for you automatically. If doing it manually instead, use the `id` and
`access_token` from the `/me/accounts` response in step 6:
```
FACEBOOK_PAGE_ACCESS_TOKEN=<the "access_token" field from /me/accounts>
FACEBOOK_PAGE_ID=<the "id" field from that same entry>
```

## What happens once this is set

`instagram_publish.py` already checks for these two variables on every run. If they're
present, it posts to both Instagram and Facebook for each due post; if either platform
fails while the other succeeds, only the failed one is retried on the next run (tracked
via the `instagram_status` / `facebook_status` columns in `upload_manifest.csv`,
independently, alongside `instagram_post_id` / `facebook_post_id` / `published_at`). If
these variables are left blank, it just posts to Instagram as before — nothing breaks
either way.

## One display difference worth knowing

Facebook doesn't have a native swipeable carousel for Page feed posts via the API —
`attached_media` produces Facebook's own standard multi-photo post instead. Same 5
images, same caption, just Facebook's own presentation rather than Instagram's
carousel UI. Worth a quick look at the first real post once it's live to confirm
you're happy with how it displays.
