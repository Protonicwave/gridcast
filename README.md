# Gridcast

Gridcast tells each of the 14 regions of Great Britain when its electricity will be cleanest in the next 48 hours, and measures how good that advice is.

This repository holds the collector, which archives NESO's Carbon Intensity forecast every half hour, the API that serves a region's cleanest windows from that archive, the React site in `web/` that shows London's, and the interface mock-up the site was ported from.

## Install

Needs Python 3.12 or later with [uv](https://docs.astral.sh/uv/), Node.js 22 or later, and Docker for the local PostgreSQL the tests use.

```sh
uv sync
npm install
npm ci --prefix web
```

## Configure

`GRIDCAST_DATABASE_URL` is the archive's PostgreSQL connection URL, for example `postgresql://gridcast@127.0.0.1:5432/gridcast` for the local database below.

Optional:

- `GRIDCAST_HEALTHCHECK_URL`: an https URL `gridcast-collect` requests after each run that stores the regional forecast.
- `GRIDCAST_COLLECTOR_PASSWORD`: when set, `gridcast-migrate` lets the role `gridcast_collector` log in with this password.
- `GRIDCAST_READER_PASSWORD`: likewise for the read-only role `gridcast_reader`, which the API connects as.
- `GRIDCAST_ALLOWED_ORIGIN`: the one browser origin the API allows, for example `https://protonicwave.github.io`. Required by `gridcast.api:app_from_environment`.

## Run

Start the local PostgreSQL 17, create the archive's tables, then fetch and store the regional forecast, the national forecast and the last 24 hours of national actuals:

```sh
docker compose up -d --wait db
export GRIDCAST_DATABASE_URL=postgresql://gridcast@127.0.0.1:5432/gridcast
uv run gridcast-migrate
uv run gridcast-collect
```

`gridcast-collect` exits 1 if any fetch, parse or write failed, and 2 if `GRIDCAST_DATABASE_URL` is unset or `GRIDCAST_HEALTHCHECK_URL` is not an https URL with a host. Each call is stored on its own, with the raw response even when it does not parse. The view `collection_coverage` gives the share of half hours with a regional forecast recorded per UTC day, and `forecast_value` lists every forecast intensity with its horizon. The test suite empties this database, so do not keep data in it.

Serve a region's outlook, the forecast from the current half hour with its cleanest and dirtiest windows, from the archive:

```sh
export GRIDCAST_ALLOWED_ORIGIN=http://127.0.0.1:5173
uv run uvicorn --factory gridcast.api:app_from_environment
curl http://127.0.0.1:8000/regions/13/outlook
```

`/regions/<1 to 14>/outlook` answers 404 for another number, 422 for a value that is not an integer, and 503 when the archive holds no usable forecast or cannot be read.

`/accuracy/national` reports NESO's national forecast error for lead times of 1 to 6, 6 to 12, 12 to 24 and 24 to 48 hours, with a 95% interval for each and for the difference between the last and the first once seven days are usable. `?until=YYYY-MM-DD` stops the evaluation before that UTC day; it never reads the day under way. A day is used only when all 48 actuals are stored and every band holds at least 90% of its nominal pairs; the others are listed with the reason. It answers 422 for a malformed `until` and 503 when the archive cannot be read.

Serve the site against that API. The dev server forwards `/regions` to `127.0.0.1:8000`, so no cross-origin setting is needed:

```sh
npm --prefix web run dev
```

For a build that calls a deployed API instead, set `VITE_GRIDCAST_API_URL` to its origin: `VITE_GRIDCAST_API_URL=<origin> npm --prefix web run build`. The page fetches the outlook on load and again when it becomes visible after ten minutes. It abandons a request after 10 seconds, so a slow start would show the unavailable state with a retry button.

Open `mockup/mockup.html` in a browser. The postcode lookup calls NESO's Carbon Intensity API, so it needs a network connection; everything else works offline.

To rebuild the page's data from the files in `data/`:

```sh
uv run gridcast-snapshot --fetched-at 2026-11-17T11:50Z data/regional_fw48h_20261117T1150Z.json data/gb-dno-license-areas-20240503.geojson data/pilot_national_2025.json mockup/snapshot.js
```

## Image

`Dockerfile` installs the locked runtime dependencies and builds two images that run as an unprivileged user. The default target, `collector`, runs `gridcast-collect`; the `api` target serves the outlook on port 8000:

```sh
docker build -t gridcast-collector .
docker run --rm -e GRIDCAST_DATABASE_URL gridcast-collector
docker build --target api -t gridcast-api .
docker run --rm -p 127.0.0.1:8000:8000 -e GRIDCAST_DATABASE_URL -e GRIDCAST_ALLOWED_ORIGIN gridcast-api
```

Inside a container, `127.0.0.1` is the container itself: point `GRIDCAST_DATABASE_URL` at the local database through the compose network (`--network gridcast_default` and host `db`).

On each pull request, GitHub Actions runs the checks below, builds both images and checks the API image answers from a freshly migrated archive. On `main` it also pushes `ghcr.io/protonicwave/gridcast-collector:<commit sha>` and `ghcr.io/protonicwave/gridcast-api:<commit sha>`. To run the whole pipeline for a branch before merging it, run `gh workflow run ci --ref <branch>`. That deploys the branch to production, so it works only for branches the environments `production` and `github-pages` allow.

## Deploy

The collector runs on Azure as a Container Apps job at 5 and 35 minutes past each hour, UTC, writing to a PostgreSQL 17 flexible server. The container app `ca-gridcast-api` serves the outlook from the same server as the read-only role, keeping one replica running so there is no cold start. Every resource is in Norway East, and `infra/` describes them in Terraform. The server accepts connections from Azure services only, other customers' included, so its passwords are the barrier. A second job, started by hand, applies migrations from inside Azure.

Needs the Azure CLI, logged in with `az login`, and Terraform 1.17. Once per subscription, register the resource providers and create the storage for Terraform's state, which holds the database passwords:

```sh
for namespace in Microsoft.App Microsoft.OperationalInsights Microsoft.DBforPostgreSQL Microsoft.Storage Microsoft.ManagedIdentity; do
  az provider register --namespace "$namespace"
done
az group create --name rg-gridcast-tfstate --location norwayeast
az storage account create --name stgridcasttfstate --resource-group rg-gridcast-tfstate \
  --location norwayeast --sku Standard_LRS --min-tls-version TLS1_2 --allow-blob-public-access false
az storage container create --name tfstate --account-name stgridcasttfstate --auth-mode key
```

Storage account names are global, so a fork picks its own and changes it in `infra/main.tf` too, along with the image owner in `infra/variables.tf`.

To deploy images CI has published, then apply any new migrations:

```sh
export ARM_SUBSCRIPTION_ID="$(az account show --query id --output tsv)"
export TF_VAR_healthcheck_url=<the check's ping URL>
terraform -chdir=infra init
terraform -chdir=infra apply \
  -var collector_image=ghcr.io/protonicwave/gridcast-collector:<commit sha> \
  -var api_image=ghcr.io/protonicwave/gridcast-api:<commit sha>
az containerapp job start --name caj-gridcast-migrate --resource-group rg-gridcast
terraform -chdir=infra output api_url
```

The migrate job runs the API image, which holds the same package as the collector's, so a migration needs no new collector image. It connects as the server's admin, applies pending migrations and lets the collector's and the API's roles log in with passwords Terraform generated. The collector's role may only insert and select, and update actuals; the API's may only select forecasts and when they were fetched. `api_image` sets the API app's image only when the app is created: later images go to it with `az containerapp update`.

The API's budget is a median under 500 ms for London's outlook over 20 warm requests. This measures it, and reports the first request separately because it includes a cold start if the app has been scaled to zero; it exits 1 over budget:

```sh
uv run python scripts/time_outlook.py "$(terraform -chdir=infra output -raw api_url)"
```

`--path` times another path (written without its leading slash, which Git Bash would rewrite) and `--budget-ms` sets its limit. The accuracy endpoint's budget is a median under 1000 ms:

```sh
uv run python scripts/time_outlook.py "$(terraform -chdir=infra output -raw api_url)" --path accuracy/national --budget-ms 1000
```

## Site

The site is published to GitHub Pages at `https://protonicwave.github.io/gridcast/`. On `main`, after the gates and the image publish, CI runs three jobs in order:

1. `deploy-api` signs in to Azure as the deploy identity, points `ca-gridcast-api` at the commit's image and waits for London's outlook to answer 200.
2. `deploy-site` builds the site with the API's origin and publishes it.
3. `smoke` runs `npm --prefix web run smoke`, a Playwright test that opens the published page and expects London's answer and a drawn series. Run it by hand with `SITE_URL=<page url> npm --prefix web run smoke` after `npx playwright install chromium`.

The jobs need configuration in the repository, set once:

- Pages with its source set to GitHub Actions.
- Environments `production`, which holds the variables below and is the subject the Azure identity trusts, and `github-pages`.
- Variables `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` and `AZURE_SUBSCRIPTION_ID` on `production`, from `terraform -chdir=infra output deploy_client_id`, `tenant_id` and `subscription_id`.
- Repository variable `GRIDCAST_API_URL`, from `terraform -chdir=infra output api_url`.

CI deploys the API image but does not run migrations. Before merging a commit that adds one, start the migrate job as in Deploy.

The API's origin is built into the page, and the API allows only the Pages origin, so a custom domain needs `GRIDCAST_ALLOWED_ORIGIN` changed in `infra/` as well.

Budgets for the page: the compressed script at most 75 KiB, and on Lighthouse mobile an LCP of at most 2.5 s and a CLS of at most 0.1. `npm --prefix web run build` prints the script's gzipped size.

## Monitor

A [healthchecks.io](https://healthchecks.io/) check with a 30-minute period and a 45-minute grace time receives a ping each time a run stores the regional forecast. It emails when no ping has arrived for 75 minutes, which also covers a job that never started. Its ping URL is a secret: keep it in the git-ignored `.env` as `TF_VAR_healthcheck_url`, not under the collector's own variable name, so a local run never pings the production check.

Recent runs and their outcome:

```sh
az containerapp job execution list --name caj-gridcast-collect --resource-group rg-gridcast --output table
```

Each run logs one `fetch stored` line per call, with its status, attempts and `duration_ms`, then `run finished` with the total seconds. The logs reach the Log Analytics workspace `log-gridcast` a few minutes later:

```kusto
ContainerAppConsoleLogs_CL
| where ContainerJobName_s == "caj-gridcast-collect"
| project TimeGenerated, Log_s
| order by TimeGenerated desc
```

The server's `storage_used` metric includes the write-ahead log and system databases, so measure the archive itself from inside Azure: save this as `query.yaml`, with the deployed image tag, and start a one-off run of the collector job with it. The output appears in the logs above.

```yaml
containers:
  - name: collect
    image: ghcr.io/protonicwave/gridcast-collector:<commit sha>
    command:
      - python
      - -c
      - |
        import os, psycopg
        with psycopg.connect(os.environ["GRIDCAST_DATABASE_URL"]) as c:
            print("archive size_bytes", c.execute("select pg_database_size(current_database())").fetchone()[0])
            print("coverage", c.execute("select * from collection_coverage").fetchall())
    env:
      - name: GRIDCAST_DATABASE_URL
        secretRef: database-url
    resources:
      cpu: 0.25
      memory: 0.5Gi
```

```sh
az containerapp job start --name caj-gridcast-collect --resource-group rg-gridcast --yaml query.yaml
```

## Test

The suite needs the local database. A bare `pytest` starts it, and Docker Desktop on Windows, when it is down; elsewhere run `docker compose up -d --wait db` first.

```sh
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run vulture src --min-confidence 80
uv run sqlfluff lint src/gridcast/migrations
npm run typecheck
npm --prefix web run test
npm --prefix web run lint
npm --prefix web run typecheck
npm --prefix web run knip
```

## Data

- `data/regional_fw48h_*.json`: the regional 48-hour forecast from the [Carbon Intensity API](https://carbonintensity.org.uk/), NESO, CC BY 4.0, fetched at the time in the file name.
- `data/gb-dno-license-areas-20240503.geojson`: the 14 distribution network operator areas in British National Grid coordinates, NESO Data Portal, NESO Open Data Licence.
- `data/pilot_national_2025.json`: the 2025 pilot comparison of NESO's national forecast with its actual.
