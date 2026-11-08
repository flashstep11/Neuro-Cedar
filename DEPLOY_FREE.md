# Deploying Cedarline for free

Two free pieces: a **Postgres database** (holds everything) and a **Render free web service** (runs the app).
Nothing depends on a disk or on your laptop being on.

> I could not confirm from the provider pages whether sign-up needs a card. Both
> are normally free-tier sign-ups, but check at sign-up. If either insists on a
> card, stop there and ask.

## 1. Create the free database

Any Postgres works. Two common free ones:

**Neon** (neon.com): create a project, then copy the **connection string**
(Dashboard → Connect). Use the **direct** one (host without `-pooler`). It looks like
`postgresql://user:password@ep-xxxx.region.aws.neon.tech/neondb?sslmode=require`.
Free plan: 1 GB, and the database sleeps after 5 idle minutes. The app reconnects
automatically (see "Sleeping databases" below).

**Supabase**: Project → Connect → copy the **session pooler** string (works over IPv4).
Free plan: 500 MB.

Keep the string secret: anyone with it can read the data.

## 2. Create the Render service

1. Push this repo to GitHub (done: `flashstep11/Neuro-Cedar`).
2. render.com → **New → Blueprint** → pick the repo. `render.yaml` sets up a **Free** web service.
   (If you prefer: **New → Web Service**, Runtime *Python*, Instance type *Free*,
   Build `pip install -r requirements.txt`, Start `otree prodserver 0.0.0.0:$PORT`.)
3. When asked, fill in the two secret values:
   - `OTREE_ADMIN_PASSWORD`: a strong password you will use to log in as `admin`
   - `DATABASE_URL`: the connection string from step 1
4. Deploy. The first start creates every table by itself. No shell commands are needed.

The app refuses to start on Render without `DATABASE_URL`, so study data can never
silently end up on Render's wiped disk.

## 3. Run the pilot

1. Open `https://<your-service>.onrender.com`, log in (`admin` + your password).
2. **Sessions → Create new session → Cedarline Study (balanced assignment)**, about 15 participants.
3. Copy the **session-wide link** and send it to participants.
4. **Wake the service first.** Free services sleep after 15 idle minutes and take about a
   minute to wake. Open the URL yourself 2 minutes before the session starts.
   Do not let the first participant be the one who wakes it.
5. Watch **Monitor** and **Report** on the session page. Cell balance and attrition only; no outcomes by condition until collection closes.

## 4. Get your data out (do this regularly)

Admin → **Data** → download the CSV (the *custom export* is the analysis-ready one).
Also download after every session. Free databases are not backed up.
If you ever lose the database, the study state is gone with it.

## Sleeping databases

Free Postgres hosts (Neon after 5 minutes) drop every connection when idle. oTree keeps
one long-lived connection, so without a fix the first participant after a quiet period
would get a server error. `settings.py` pings the connection on every checkout and
reconnects transparently. This was tested by killing every database connection and then
running participants through a real browser: zero errors. `state_store.py` does the same
for assignment, pool sequence and lottery storage (it retries a dropped connection).

## Things to know

- **Changing the data model later** (adding a field) needs a fresh database; oTree creates
  tables but does not alter existing ones. Freeze fields before the pilot. A fresh database also
  starts a fresh pool sequence and assignment counts.
- **Lottery contacts** live in their own table (`lottery_entries`) that oTree's export never reads.
  For physical separation, create a second free database and set `LOTTERY_DATABASE_URL`.
- **Pilot vs main study:** use a different database for each so pilot data, counts and
  sequence positions can never leak into the main study.
- **Local development** needs no database setup: with no `DATABASE_URL` it uses local SQLite files.
- Verify the state layer any time with `python qa/test_state_store.py`
  (and against Postgres with `STATE_DATABASE_URL=... CL_TEST_RESET=1`; this drops its own two tables).
