# Legacy data migration

The ignored `db.sqlite3` contains historical participant data. It must not be copied into a
container image or used as the first place to test a schema migration.

The new Django migrations preserve the legacy records by importing each participant's old
per-group sessions into an archived protocol-v1 study run. The recorded group order is inferred
from the original session primary-key order. Original response text, selections, sequence values,
primary keys, and relationships remain available for provenance; normalized response-time and
selection fields are added alongside them.

## 1. Freeze and back up

Stop anything writing to the SQLite database. Create the backup on encrypted storage outside the
repository:

```bash
sqlite3 -readonly db.sqlite3 ".backup '/secure/path/drugid-before-migration.sqlite3'"
sha256sum db.sqlite3 /secure/path/drugid-before-migration.sqlite3
sqlite3 -readonly /secure/path/drugid-before-migration.sqlite3 'PRAGMA integrity_check;'
```

Record baseline row counts without printing participant details:

```bash
sqlite3 -readonly /secure/path/drugid-before-migration.sqlite3 \
  "SELECT 'participants', count(*) FROM DrugID_API_user
   UNION ALL SELECT 'group sessions', count(*) FROM DrugID_API_session
   UNION ALL SELECT 'trials', count(*) FROM DrugID_API_set
   UNION ALL SELECT 'results', count(*) FROM DrugID_API_result;"
```

Keep the original database read-only. Make a second working copy from the backup for the next
step.

## 2. Prove the migrations on the copy

Use an absolute path with four slashes after `sqlite:`:

```bash
cp /secure/path/drugid-before-migration.sqlite3 /secure/path/drugid-migration-test.sqlite3
DATABASE_URL=sqlite:////secure/path/drugid-migration-test.sqlite3 \
SECRET_KEY=migration-test-only \
DEBUG=True \
uv run python manage.py migrate --noinput

DATABASE_URL=sqlite:////secure/path/drugid-migration-test.sqlite3 \
SECRET_KEY=migration-test-only \
DEBUG=True \
uv run python manage.py check
```

Re-run the counts and `PRAGMA integrity_check`. Expected historical application counts for the
database currently in this project are 12 participants, 34 group attempts, 1,710 trials, and
1,642 results. There should also be 12 archived study runs, 1,642 normalized response times,
1,642 trials linked through their result, and 68 deliberately unlinked unanswered trials.

Do not continue if a count changes unexpectedly.

## 3. Export only the study application

After validation, export from the migrated copy to an encrypted location:

```bash
DATABASE_URL=sqlite:////secure/path/drugid-migration-test.sqlite3 \
SECRET_KEY=migration-test-only \
DEBUG=True \
uv run python manage.py dumpdata DrugID_API --indent 2 \
  --output /secure/path/drugid-study-data.json
```

The JSON contains email addresses and research results. Restrict its permissions and delete it
securely when the transfer has been verified.

## 4. Load a fresh PostgreSQL database

Do this before starting the normal `web` service, because its entrypoint also synchronizes the
canonical image assets.

```bash
docker compose up -d db

docker compose run --rm \
  -e RUN_MIGRATIONS=0 -e LOAD_STUDY_ASSETS=0 \
  web python manage.py migrate --noinput

docker compose run --rm \
  -e RUN_MIGRATIONS=0 -e LOAD_STUDY_ASSETS=0 \
  -v /secure/path:/import:ro \
  web python manage.py loaddata /import/drugid-study-data.json

docker compose up -d web
```

Create a fresh Django administrator rather than transferring old authentication sessions:

```bash
docker compose exec web python manage.py createsuperuser
```

Compare PostgreSQL counts with the baseline and inspect representative CSV exports in admin.
Keep the immutable SQLite backup until the deployed database has been backed up and independently
verified.

If the source database has received any protocol-v2 registrations, stop and adapt the export to
include their linked Django auth users before loading it. The procedure above is intentionally
scoped to the legacy database currently present in this workspace, whose participants have no
linked auth accounts.
