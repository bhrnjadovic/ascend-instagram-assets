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
6. Still in Graph API Explorer, change the **User or Page** dropdown (near the token
   field) to select your actual Facebook Page — this swaps in a **Page access token**
   rather than your personal user token. This is the value you need.
7. Find your Page's numeric ID: query `GET /me/accounts` — the response lists your
   pages with their `id` and `access_token` fields. The `access_token` shown there is
   already a long-lived Page token in most cases (Page tokens derived from a long-lived
   user session typically don't expire on the usual 60-day cycle the way user tokens
   do — no refresh logic has been built for this one, since it isn't needed the same way).

## What to hand back

Add to `.env` yourself (don't paste in chat):
```
FACEBOOK_PAGE_ACCESS_TOKEN=<the page access token from step 6/7>
FACEBOOK_PAGE_ID=<the numeric page id from step 7>
```

## What happens once this is set

`instagram_publish.py` already checks for these two variables on every run. If they're
present, it posts to both Instagram and Facebook for each due post; if either platform
fails while the other succeeds, only the failed one is retried on the next run (tracked
via the `ig_status` / `fb_status` columns in `upload_manifest.csv`, independently). If
these variables are left blank, it just posts to Instagram as before — nothing breaks
either way.

## One display difference worth knowing

Facebook doesn't have a native swipeable carousel for Page feed posts via the API —
`attached_media` produces Facebook's own standard multi-photo post instead. Same 5
images, same caption, just Facebook's own presentation rather than Instagram's
carousel UI. Worth a quick look at the first real post once it's live to confirm
you're happy with how it displays.
