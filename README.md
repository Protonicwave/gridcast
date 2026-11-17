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

## Run

Start the local PostgreSQL 17, create the archive's tables, then fetch and store the current regional forecast:

```sh
docker compose up -d --wait db
export GRIDCAST_DATABASE_URL=postgresql://gridcast@127.0.0.1:5432/gridcast
uv run gridcast-migrate
uv run gridcast-collect
```

`gridcast-collect` exits 1 if the fetch, the parse or the write failed, and 2 if `GRIDCAST_DATABASE_URL` is unset. The raw response is stored even when it does not parse. The test suite empties this database, so do not keep data in it.

Open `mockup/mockup.html` in a browser. The postcode lookup calls NESO's Carbon Intensity API, so it needs a network connection; everything else works offline.

To rebuild the page's data from the files in `data/`:

```sh
uv run gridcast-snapshot --fetched-at 2026-11-17T11:50Z data/regional_fw48h_20261117T1150Z.json data/gb-dno-license-areas-20240503.geojson data/pilot_national_2025.json mockup/snapshot.js
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
