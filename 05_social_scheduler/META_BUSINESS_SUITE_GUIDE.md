# Uploading and Scheduling All 200 Posts in Meta Business Suite

Free, official, no developer setup. Manual per-post entry — there's no bulk/CSV import
into Business Suite's scheduler, so this is real data entry, but each post takes only a
couple of minutes once you're used to the pattern.

## What's ready for you

Every post folder in `03_generated_posts/{post_id}_{slug}/` now contains:
- `{post_id}_slide-01.png` through `_slide-05.png` — upload in this exact numeric order
- **`caption_full.txt`** — caption **and** hashtags already combined, ready to paste as-is.
  (`caption.txt` alone is just the caption without hashtags — use `caption_full.txt`, not
  `caption.txt`, so you don't have to copy hashtags separately.)

`05_social_scheduler/posting_schedule.csv` is your master calendar — one row per post,
with its scheduled date, time, and folder path. Open it in Excel/Google Sheets and work
through it top to bottom, marking each row's `status` as `scheduled` once done, so you
always know where you left off.

## One-time setup (do this first)

1. Go to **business.facebook.com** and log in.
2. **Settings → Accounts → Instagram accounts** — confirm your Instagram account shows as
   connected. If not, connect it there first (it must be a Professional/Business account).
3. Check **Settings → Business info → time zone** is set correctly (e.g. an Australian time
   zone) — the `scheduled_time` values in the calendar are plain local times, so Business
   Suite needs to be set to the same time zone you intend them for, or every post will land
   at the wrong hour.

## Per-post steps (repeat for each row in posting_schedule.csv)

1. In Business Suite, go to **Planner** in the left sidebar (or **Create post** if Planner
   isn't visible in your layout).
2. Click **Create post** → choose **Instagram** as the destination (deselect Facebook
   unless you also want it cross-posted).
3. Click **Add photos/videos** and select all 5 slide PNGs from that post's folder **at
   once**, in a single file dialog — most file pickers preserve the order you select them
   in, so select `_slide-01` first, then 02, 03, 04, 05 in order. After adding, Business
   Suite shows thumbnails in a row — **visually confirm slide 1 is leftmost** before moving
   on, since a misordered carousel is hard to notice later.
4. If a crop/aspect-ratio prompt appears, choose **4:5 (portrait)** — the slides are
   designed edge-to-edge at that ratio; a square (1:1) crop will cut off content.
5. Open `caption_full.txt` from that post's folder, select all, copy, and paste it into
   the caption box in Business Suite.
6. Find **Schedule** (not **Publish**) in the post options, and enter the date/time from
   that row in `posting_schedule.csv`.
7. Click **Schedule**. Business Suite will confirm it's queued.
8. Back in `posting_schedule.csv`, change that row's `status` from `pending` to
   `scheduled`.

## Pacing this across sessions

- Do it in batches of ~15-25 posts per sitting. Business Suite also throttles new
  schedules to roughly 25/day, so pushing past that in one sitting may just get rejected
  or queued oddly — spreading it over a few sessions avoids that entirely.
- At 200 posts, expect **roughly 5-8 sessions** of 30-45 minutes each, depending on how
  quickly you move through the copy/paste/schedule rhythm.
- Because this calendar was deliberately compressed to fit inside Business Suite's 75-day
  scheduling limit (200 posts run Aug 3 - Oct 9, 2026 at 4/day), once every row is
  scheduled, **you're fully done** — no need to return in a few months to schedule more.

## Before you commit to all 200: test the first one

Schedule just **ALP-175** (the first row) and let it actually go out, or at minimum
preview it fully in Business Suite's post preview. Confirm:
- All 5 slides appear in the right order and aren't cropped
- The caption and hashtags both came through
- The scheduled time lands correctly against your business's actual time zone

Once that one looks right, the rest will behave identically — worth the two minutes
before committing to 200 rounds of data entry.

## If you change the cadence or start date later

Regenerate the calendar (this also regenerates `caption_full.txt` in every folder, so
it's always safe to re-run):
```
python scripts/build_schedule.py --start-date 2026-08-03 --posts-per-day 4
```
Keep posts-per-day high enough to still fit inside 75 days if you want the whole thing
schedulable in one pass — 200 posts ÷ 75 days ≈ 2.7/day minimum across all 7 days, or
~4/day if you keep it weekdays-only (as it's currently set).
