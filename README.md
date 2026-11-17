# Gridcast

Gridcast tells each of the 14 regions of Great Britain when its electricity will be cleanest in the next 48 hours, and measures how good that advice is.

This repository currently holds the interface mock-up: a static page built from a saved snapshot of NESO's Carbon Intensity forecast.

## Install

Needs Python 3.12 or later with [uv](https://docs.astral.sh/uv/), and Node.js for the type check.

```sh
uv sync
npm install
```

## Run

Open `mockup/mockup.html` in a browser. The postcode lookup calls NESO's Carbon Intensity API, so it needs a network connection; everything else works offline.

To rebuild the page's data from the files in `data/`:

```sh
uv run gridcast-snapshot --fetched-at 2026-11-17T11:50Z data/regional_fw48h_20261117T1150Z.json data/gb-dno-license-areas-20240503.geojson data/pilot_national_2025.json mockup/snapshot.js
```

## Test

```sh
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run vulture src --min-confidence 80
npm run typecheck
```

## Data

- `data/regional_fw48h_*.json`: the regional 48-hour forecast from the [Carbon Intensity API](https://carbonintensity.org.uk/), NESO, CC BY 4.0, fetched at the time in the file name.
- `data/gb-dno-license-areas-20240503.geojson`: the 14 distribution network operator areas in British National Grid coordinates, NESO Data Portal, NESO Open Data Licence.
- `data/pilot_national_2025.json`: the 2025 pilot comparison of NESO's national forecast with its actual.
