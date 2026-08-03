# Ampoule reaction-time study

This repository now contains the complete study application: a Django API/admin site, the
Vue participant interface, the ampoule image set, and a Docker deployment.

Participants register with their email, speciality, and years of experience. The application
creates a study run immediately, snapshots the current protocol settings, and stores a random
order containing each of the three label groups exactly once. A one-use magic link signs the
participant in. Trial progress is held on the server, so refreshing the page resumes the same
trial instead of losing progress or creating duplicates.

## Start with Docker

Requirements: Docker with the Compose plugin.

1. Copy `.env.example` to `.env`.
2. Replace both placeholder secrets in `.env`. Keep `DATABASE_URL` and the PostgreSQL password
   in sync.
3. Start the application:

   ```bash
   docker compose up --build
   ```

4. Create an administrator:

   ```bash
   docker compose exec web python manage.py createsuperuser
   ```

Open <http://localhost:8000> for the participant site and
<http://localhost:8000/admin/> for Django admin.

The example environment uses Django's console email backend. Follow the magic link printed by
`docker compose logs web`. For a real deployment, configure SMTP and set `PUBLIC_APP_URL` to the
public HTTPS origin.

## Configure the experiment

In Django admin, open **Experiment configuration** and set:

- **Trials per group** — how many reaction-time trials each participant completes in each style.
- **Choices per trial** — how many ampoules are displayed (maximum 20 with the current assets).
- **Time limit (ms)** — how long a participant has to answer each trial.
- **Tutorial trials** — how many timed practice trials appear before measured data collection
  (5–10; default 6).

Settings are copied onto a run at registration. Editing the configuration therefore affects new
registrations without changing an experiment already in progress. The defaults are 50 trials per
group, 8 choices, 3,000 ms, and 6 tutorial trials. Runs created before the tutorial was introduced
retain a zero-trial tutorial snapshot and remain distinguishable from tutorial-exposed cohorts.

Results can be filtered and downloaded as CSV from the admin. Participant and result APIs are not
publicly listable.

## Statistical analysis

The repository includes a reproducible publication-analysis pipeline based on participant-clustered
generalised estimating equations. It reports global display-style tests, adjusted pairwise effects,
p values, 95% confidence intervals, training/fatigue and period interactions, timeout-censored
time-to-response sensitivity, participant-paired figures, and generated methods/results drafts.
Tutorial responses are practice data: they are stored separately for operational progress, but
are deliberately excluded from measured-study snapshots, outcome tables, figures, and GEE models.
The snapshot configuration signature records the required tutorial length so tutorial and
no-tutorial cohorts cannot be silently treated as the same protocol configuration.

Use the dedicated pseudonymised snapshot command instead of the operational admin CSV:

```bash
ANALYSIS_PSEUDONYM_KEY='replace-with-a-secret-of-at-least-32-bytes' \
uv run python manage.py export_analysis_snapshot \
  --output analysis/data/protocol-2-snapshot \
  --strict

MPLCONFIGDIR=/tmp/ampoule-matplotlib \
uv run python -m analysis.ampoule_analysis \
  --input analysis/data/protocol-2-snapshot \
  --output analysis/build/protocol-2-results \
  --strict
```

See the [analysis README](analysis/README.md) and
[statistical analysis plan](analysis/STATISTICAL_ANALYSIS_PLAN.md) before interpreting outputs.
Legacy protocol-1 results require `--legacy-pilot` and are never pooled with protocol 2.

## Local development

Backend (Python 3.14 and `uv`):

```bash
uv sync --all-groups --frozen
export DEBUG=True
export SECRET_KEY='local-development-only-secret-key-with-at-least-fifty-characters'
export PUBLIC_APP_URL='http://localhost:5173'
export CSRF_TRUSTED_ORIGINS='http://localhost:5173'
export SHOW_DEBUG_MAGIC_LINK=True
uv run python manage.py migrate
uv run python manage.py insert_assets
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

Frontend (Node 24):

```bash
cd frontend
npm ci
npm run dev
```

In this two-process setup, the development magic link opens Vite at <http://localhost:5173>.
Vite proxies `/api` and `/static` to Django. The production image builds the frontend and serves
it from the same origin through Django and WhiteNoise, so production CORS configuration is not
needed.

## Verification

```bash
uv run ruff check DrugID DrugID_API analysis docker manage.py --exclude DrugID_API/migrations
uv run python manage.py makemigrations --check --dry-run
uv run pytest

cd frontend
npm run lint
npm run typecheck
npm run test
npm run build
```

CI runs the same checks against PostgreSQL and builds the production container.

## Production checklist

- Use fresh, random Django and PostgreSQL secrets; never reuse the key from the old source tree.
- Set `DEBUG=False`, the real `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, and HTTPS
  `PUBLIC_APP_URL`.
- Configure a transactional SMTP provider and a real `DEFAULT_FROM_EMAIL` address.
- Put the application behind a trusted reverse proxy and enforce an IP rate limit on
  `/api/auth/magic-link/`; the application also applies per-address issuance limits.
- Terminate TLS at the platform/load balancer, enable the secure-cookie/redirect settings from
  `.env.example`, and only then enable HSTS.
- When replacing an older deployment, purge any CDN cache of the former public
  `/static/{style}/{drug}.png` paths. Study images are now private, non-cacheable responses tied
  to the participant's outstanding trial.
- Back up PostgreSQL and restrict access to exports because they contain participant data.
- Run `python manage.py check --deploy` with the production environment before release.

The ignored legacy `db.sqlite3` is deliberately excluded from Docker images. Its historical
results are preserved by the new migrations; see [Legacy data migration](docs/legacy-data-migration.md)
before moving that data to PostgreSQL.

## Repository layout

- `DrugID/` — Django project settings and routing.
- `DrugID_API/` — study models, APIs, admin, migrations, tests, and canonical ampoule images.
- `frontend/` — Vue 3/Vite participant application.
- `analysis/` — pseudonymised snapshot validation, GEE/sensitivity models, figures, tests, and SAP.
- `docker/`, `Dockerfile`, `compose.yaml` — production runtime and local deployment.
- `.github/` — CI and dependency update configuration.

Licensed under the MIT License. The imported frontend retains its original license in
`frontend/LICENSE`.
