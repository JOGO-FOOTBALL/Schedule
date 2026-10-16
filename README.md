# Schedule · 433 ⚽

A web app (Streamlit) for the 433 social media team. It does two things:

1. **Match calendar**: the matches of the clubs and countries we follow, week by week, with club logos.
2. **Schedule**: who works when (Night 00–09, Day 09–17, Evening 16–00) and on which channel (Main, App, NL).
   On request the app builds a proposed schedule that follows every rule. You can then adjust it by hand
   and send it to Shiftbase one week at a time.

The schedule is shown inside the calendar: for each day you see who is working on the left and the matches on the right.

---

## In short: how does it work?

Step by step, this is what happens when someone opens the app:

1. **Log in**: `auth.py` lets you log in with the same account as the expense-claim-generator.
2. **Load data**: `storage.py` reads the team, the rules, time off and the schedule from CSV files in `data/`.
3. **Fetch matches**: `matches.py` gets the matches from the database (Azure SQL) through `db.py`.
   `clubs.py` decides which clubs we follow.
4. **Logos**: `logos.py` creates temporary links to the club logos in Azure Blob Storage.
5. **Draw the calendar**: `calendar_view.py` builds the calendar (HTML) with matches, schedule and the hours column.
6. **Show it**: `main.py` puts everything on screen, with tabs for the team, rules, time off and so on.
7. **Make a schedule** (only after clicking *Make schedule*): `scheduler.py` and `optimizer.py` work out
   a schedule that follows all the rules. It is saved again through `storage.py`.
8. **Drag or remove someone** in the calendar: `main.py` checks with `scheduler.py` whether it is allowed,
   saves it and redraws the calendar.
9. **To Shiftbase**: the *Send to Shiftbase* button next to a week makes `shiftbase.py` send only the
   **new** shifts of that week to Shiftbase. Anything already in Shiftbase is never changed or deleted.

Secrets (passwords, keys) come from `.env` or Azure Key Vault, through `config.py`.

---

## Every file, one by one

### The code: `src/`

| File | What it does |
|---|---|
| `main.py` | **The app itself.** This is where it starts. Builds every screen: the calendar with the schedule (tab *Matches*), the same calendar with what is in Shiftbase now (tab *Shiftbase*, read only) and the tabs *Special events*, *Employees*, *Zero hours*, *Staffing rules* and *Time off*. Also handles every click: dragging, ×, +, changing a channel, filling open slots, the Shiftbase dialog. |
| `calendar_view.py` | **Draws the calendar** as HTML in 433 style (black, white, neon yellow). Per day the rows Night/Day/Evening with the people, the match cards with logos, red "open" slots, and per week the hours column (red = too few hours, orange = too many). |
| `scheduler.py` | **The scheduling rules.** Knows how many people are needed per day, shift and channel, and checks whether a schedule breaks a rule (rest time of 11 hours, fixed in the code as `MIN_REST_HOURS`, max shifts per week, weekend rule, days off, person rules, and so on). Also contains the simple fallback planner. |
| `optimizer.py` | **The smart planner.** Uses Google OR-Tools to look at all weeks at once and find the best schedule: first as few open slots as possible, then fixed agreements, then contract hours, then preferences. If that fails, `scheduler.py` falls back to the simple planner. |
| `storage.py` | **Saving and loading.** Every table (team, rules, schedule, time off, ...) is a CSV file, in `data/` or in Azure Blob Storage (see `blob_store.py`). It also holds the default values used when a file does not exist yet (for example the team and the Shiftbase IDs), and the fixed shift times (Night 00–09, Day 09–17, Evening 16–00). |
| `blob_store.py` | **Storage in Azure Blob Storage** instead of `data/`, switched on with `SCHEDULE_BLOB_CONTAINER` and `SCHEDULE_BLOB_SAS_URL` in `.env`. Access goes through a SAS link that Azure itself limits to that one container (no delete rights), so the app cannot touch anything else, such as the expense-claim-generator logins. On top of that, the code only allows the fixed list of schedule files under `data/`. |
| `matches.py` | **Matches.** Fetches matches from `MatchDataOLAP.EventBase`, converts kick-off times to Dutch time, removes duplicate matches and decides which matches are "big" (for example El Clásico). |
| `clubs.py` | **List of clubs and countries** we follow. The order matters: top = most popular. If a day has more than 5 matches, the calendar shows the most popular ones. Want to add a club? Add it to this list. |
| `logos.py` | **Club logos.** Creates temporary read links (valid for 3 hours) to the logos in Azure Blob Storage. Nothing is downloaded. |
| `db.py` | **Database connection** to Azure SQL (the matches). Needs *ODBC Driver 18 for SQL Server*. |
| `config.py` | **Fetches secrets.** Looks for each password or key in `.env` first, then in Azure Key Vault. |
| `auth.py` | **Login.** Uses the same accounts as the expense-claim-generator (a file in the Datascience Blob Storage). For now everyone who can log in has the same rights. |
| `shiftbase.py` | **Shiftbase connection.** Reads what is in Shiftbase, compares it with our schedule and only creates new shifts. *Undo* only deletes shifts this tool created itself. Can be tested on its own: `python src/shiftbase.py`. |
| `assets/` | Images for the calendar: the Champions League starball and the Europa League logo. |
| `__pycache__/` | Created by Python itself. Leave it alone; it is not in git. |

### Files in the main folder

| File / folder | What it does |
|---|---|
| `README.md` | This file. |
| `requirements.txt` | The Python packages the app needs (Streamlit, pandas, OR-Tools, Azure, ...). |
| `Dockerfile` | Recipe for building the app into a container, including the SQL driver. |
| `compose.yaml` | Starts the app with Docker at http://localhost:8503 and mounts the `data/` folder so your data is kept. |
| `.dockerignore` | What must **not** go into the container (including `.env`, `data/`, `.git/`). |
| `.gitignore` | What must **not** go into git: `data/` (names), `.env` (passwords), `auth/` (logins), `test_logos/`. |
| `.env` | **Secret, not in git.** Passwords and keys (database, Azure, Shiftbase). Never share it. |
| `.env.example` | Example of `.env` without real values: shows which settings are needed. |
| `.streamlit/config.toml` | The 433 look of the app (colours, fonts) and automatic reload after saving. |
| `.github/workflows/build-push-image.yml` | On every push to `main`, automatically builds a new container and puts it in Azure Container Registry (ACR). |
| `.claude/settings.json` | Settings for Claude Code (the AI assistant used to work on this project). Not needed for the app. |
| `test_logos/` | Local test folder, not in git and not in the container. Not needed for the app. |
| `data/` | **The app's data** (not in git, because it contains names). See below. |
| `auth/` | Optional, not in git: a local login file `auth/config.yaml` for testing without the shared accounts. |

### The `data/` folder

This is where the app stores everything you enter in it. Each tab has its own file:

| File | Contents |
|---|---|
| `employees.csv` | The team: channels, contract hours, Shiftbase ID, fixed days off, role (e.g. intern), ... |
| `schedule.csv` | **The schedule**: per day who works which shift on which channel. |
| `staffing.csv` | How many people are needed per day type, shift and channel. |
| `match_staffing.csv` | Extra staffing for matches and events. |
| `person_rules.csv` | Person rules, e.g. "Karel only works on Main". |
| `afwezigheid.csv` | Time off and leave (whole day, day only or evening only). |
| `zero_hours.csv` | Agreed days of zero-hours employees. |
| `events.csv` | Special events (e.g. Ballon d'Or). |
| `shiftbase_sent.csv` | Which shifts this tool has sent to Shiftbase (needed for *Undo*). |

If a file does not exist yet, the app uses the default values from `storage.py`.

---

## Starting the app

### First: fill in `.env`

Copy `.env.example` to `.env` and fill in the values (ask the administrator for them):

- Match database: `MATCH_DB_SERVER`, `MATCH_DB_DATABASE`, `MATCH_DB_USERNAME`, `MATCH_DB_PASSWORD`
- Azure Key Vault (for logos and logins): `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_VAULT_URL`
- Shiftbase: `SHIFTBASE_API_KEY` (in Shiftbase: *Settings > App center > Public API*)

### With Docker (recommended)

```bash
docker compose up --build
```

Then open http://localhost:8503. After changing the code: stop with Ctrl+C and run the same command again.

### Without Docker

```bash
pip install -r requirements.txt
streamlit run src/main.py
```

This needs *ODBC Driver 18 for SQL Server* installed on your computer; without it the matches won't load.

---

## How to use the app

1. **Update the team** (tab *Employees*): channels, contract hours, Shiftbase ID, fixed days off, and so on.
2. **Enter time off** (tab *Time off*) and any zero-hours days (tab *Zero hours*).
3. **Check the rules** (tab *Staffing rules*): staffing per day type, person rules and extra staffing for matches.
4. **Make a schedule**: choose *From week* and *Until week* at the top and click **Make schedule**.
   Nothing is ever scheduled on its own: only when you click that button.
5. **Adjust in the calendar**:
   - **drag** people to another shift or day;
   - **×** to remove someone, **+** to add someone;
   - click the **channel** to change it;
   - click a red **open** slot to pick someone who is allowed to work there by the rules.

   If a change breaks a rule, the app tells you why it isn't possible.
6. **Check the hours** in the column on the right: red = under contract, orange = over contract. The reason is shown below it.
7. **See what is in Shiftbase**: the tab *Shiftbase* shows the same calendar, but with the shifts as they are in Shiftbase now (read only; *Refresh* reads it again).
8. **To Shiftbase**: click *Send to Shiftbase* next to a week. You first see what will be sent.
   Only lines with status **new** are created. *Undo* removes them again.

### Main scheduling rules

- At most 2 weekend shifts per week (Friday evening counts as weekend). After such a weekend, the weekend before and after has at most 1.
- At least 11 hours rest between shifts and no more shifts per week than set in *Employees*.
- Topping up to contract hours only happens on weekdays, preferably on shifts with many matches.
- Interns work Mon–Fri day shifts, never at weekends, and never alone on their channel.
- Champions League evening: 2 on Main, 2 on App, 2 on NL.

---

## Going live (deploy)

On every push to `main`, GitHub automatically builds a new container (see `.github/workflows/build-push-image.yml`)
and puts it in Azure Container Registry. This needs the repository secrets `ACR_SERVER`, `ACR_USERNAME` and
`ACR_PASSWORD`.

**Note:** in a container in Azure, the `data/` folder is lost on every restart. So online, store the data in
Blob Storage:

1. In the Azure portal, in the Datascience storage account, create a container `schedule-app` (private).
2. On that container, create a SAS token (*Shared access tokens*): permissions **Read, Add, Create, Write, List**
   (not Delete), an expiry date (e.g. one year, set a reminder), HTTPS only. Copy the **Blob SAS URL**.
3. Add both to `.env` (and to the settings of the app in Azure):
   `SCHEDULE_BLOB_CONTAINER=schedule-app` and `SCHEDULE_BLOB_SAS_URL=<the Blob SAS URL>`.
4. Move the current data across once, from the project folder: `python src/blob_store.py upload`.
   This only uploads files that are not in the blob yet; it never overwrites anything.
5. Check what is there: `python src/blob_store.py`.

**Safety net:** the first time a file changes on a given day, the app first keeps the old version as
`data/backup/<date>/<file>` in the same container. To go back:

- everything as it was on a day: `python src/blob_store.py restore 2026-10-15`
- only the schedule: `python src/blob_store.py restore 2026-10-15 schedule.csv`

Restoring first keeps the current version in `data/backup/before-restore/`, so a restore can be undone too.

Locally, leave both settings out: then your laptop keeps using `data/` and testing never touches the real data.
Without `SCHEDULE_BLOB_CONTAINER` the app simply uses the local `data/` folder, as before.
