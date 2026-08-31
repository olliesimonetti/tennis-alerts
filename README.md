# Tennis court alerts

A small site where you pick LTA tennis courts and the days/times you care
about (e.g. "Telegraph Hill, weekdays 17:00-19:00, or any time Sunday"), plus
a background poller that watches those courts and messages you on Telegram
the moment a matching slot opens up. No LLM calls anywhere in the running
system — it's all plain HTTP polling and rule matching, so it costs nothing
to run continuously.

## How it fits together

- **[site/](site/)** — static preferences page (`index.html` + `config.js`).
  Lets you search ~600 LTA venues (from `venues_directory.json`), pick days
  and a time window, and saves the rule to a Supabase table. Host it free on
  GitHub Pages.
- **Supabase** — a free hosted Postgres table (`alert_rules`) holding your
  saved rules. The site writes to it directly from the browser (using a
  public "anon" key — see the RLS note in `supabase_schema.sql`).
- **[check_courts.py](check_courts.py)** — reads your rules from Supabase,
  polls `https://www.lta.org.uk/api/courtdetail/availability` for each
  distinct venue you have a rule for, diffs against `state.json` (last-seen
  availability) so you're only alerted on *new* slots, and messages Telegram
  for slots matching a rule's day-of-week + time window.
- **[.github/workflows/check_courts.yml](.github/workflows/check_courts.yml)**
  — runs the poller every 15 minutes via GitHub Actions (free tier) and
  commits the updated `state.json` back to the repo.
- **[build_venue_directory.py](build_venue_directory.py)** — the one-off
  crawler that built `venues_directory.json` (612 venues) by querying LTA's
  public "Book a tennis court" search from ~110 UK towns/cities and paging
  through results. Best-effort coverage, not a literal exhaustive geographic
  grid — rerun it (and add more towns to the `TOWNS` list if needed) to
  refresh or fill gaps.

## One-time setup

### 1. Supabase (stores your alert rules)

1. Create a free project at [supabase.com](https://supabase.com) (you'll need
   to sign up yourself).
2. In the SQL Editor, run the contents of [supabase_schema.sql](supabase_schema.sql).
3. Go to Settings -> API and copy the **Project URL** and **anon public key**.
4. Paste them into [site/config.js](site/config.js).

### 2. Telegram bot (sends your alerts)

1. Message [@BotFather](https://t.me/BotFather), send `/newbot`, follow the
   prompts -> you get a bot token.
2. Message your new bot anything (e.g. "hi").
3. Visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser
   -> your chat ID is in the JSON under `message.chat.id`.

### 3. Deploy

1. Push this folder to a new GitHub repo (public or private).
2. Enable **GitHub Pages** for the repo, serving from the `site/` folder (or
   `/docs` if you rename it) — this gives you the URL where you'll manage
   your alerts.
3. In the repo's Settings -> Secrets and variables -> Actions, add:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY`
4. Open your GitHub Pages URL, add your alert(s).
5. The workflow runs automatically every 15 min (6am-9pm UTC). Trigger it
   manually from the Actions tab ("Run workflow") to test immediately.

## Local testing

```bash
export SUPABASE_URL=https://your-project.supabase.co
export SUPABASE_ANON_KEY=your-anon-key
python3 check_courts.py
```

Without `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` set, alerts print to the
console instead of sending.

To preview the site locally:

```bash
cd site && python3 -m http.server 8765
```

## Notes / limitations

- The first check for a newly-added court alerts on *all* currently
  available slots matching your rule (nothing to diff against yet) —
  expected, not a bug.
- Mini/junior courts are excluded from all matching.
- The `alert_rules` table is writable by anyone with your Supabase URL + anon
  key (both are embedded in the public site JS) — fine for a personal tool
  managing non-sensitive data, but don't put anything sensitive in it.
- This uses LTA's public JSON/HTML endpoints directly (no API key, confirmed
  via browser network inspection). If LTA changes their booking platform,
  both the poller and the venue crawler may need to be re-pointed the same
  way — inspect network requests on lta.org.uk's "Book a tennis court" page.
