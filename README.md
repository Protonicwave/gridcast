# Gridcast

Gridcast tells each of the 14 regions of Great Britain when its electricity will be cleanest in the next 48 hours, and measures how good that advice is.

This repository holds the collector, which archives NESO's Carbon Intensity forecast every half hour, and the interface mock-up: a static page built from a saved snapshot of that forecast.

## Install

Needs Python 3.12 or later with [uv](https://docs.astral.sh/uv/), Node.js for the type check, and Docker for the local PostgreSQL the tests use.

```sh
uv sync
npm install
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

On each pull request, GitHub Actions runs the checks below and builds the image. On `main` it also pushes `ghcr.io/protonicwave/gridcast-collector:<commit sha>`. To publish a branch's image before merging it, run `gh workflow run ci --ref <branch>`.

## Deploy

The collector runs on Azure as a Container Apps job at 5 and 35 minutes past each hour, UTC, writing to a PostgreSQL 17 flexible server. Every resource is in Norway East, and `infra/` describes them in Terraform. The server accepts connections from Azure services only, other customers' included, so its passwords are the barrier. A second job, started by hand, applies migrations from inside Azure.

Needs the Azure CLI, logged in with `az login`, and Terraform 1.17. Once per subscription, register the resource providers and create the storage for Terraform's state, which holds the database passwords:

```sh
for namespace in Microsoft.App Microsoft.OperationalInsights Microsoft.DBforPostgreSQL Microsoft.Storage; do
  az provider register --namespace "$namespace"
done
az group create --name rg-gridcast-tfstate --location norwayeast
az storage account create --name stgridcasttfstate --resource-group rg-gridcast-tfstate \
  --location norwayeast --sku Standard_LRS --min-tls-version TLS1_2 --allow-blob-public-access false
az storage container create --name tfstate --account-name stgridcasttfstate --auth-mode key
```

Storage account names are global, so a fork picks its own and changes it in `infra/main.tf` too, along with the image owner in `infra/variables.tf`.

To deploy an image CI has published, then apply any new migrations:

```sh
export ARM_SUBSCRIPTION_ID="$(az account show --query id --output tsv)"
export TF_VAR_healthcheck_url=<the check's ping URL>
terraform -chdir=infra init
terraform -chdir=infra apply -var collector_image=ghcr.io/protonicwave/gridcast-collector:<commit sha>
az containerapp job start --name caj-gridcast-migrate --resource-group rg-gridcast
```

The migrate job connects as the server's admin, applies pending migrations and lets the collector's role log in with a password Terraform generated. That role may only insert and select, and update actuals.

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

The suite needs the local database running (`docker compose up -d --wait db`).

```sh
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run vulture src --min-confidence 80
uv run sqlfluff lint src/gridcast/migrations
npm run typecheck
```

## Data

- `data/regional_fw48h_*.json`: the regional 48-hour forecast from the [Carbon Intensity API](https://carbonintensity.org.uk/), NESO, CC BY 4.0, fetched at the time in the file name.
- `data/gb-dno-license-areas-20240503.geojson`: the 14 distribution network operator areas in British National Grid coordinates, NESO Data Portal, NESO Open Data Licence.
- `data/pilot_national_2025.json`: the 2025 pilot comparison of NESO's national forecast with its actual.
