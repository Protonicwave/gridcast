create table api_fetch (
    fetch_id bigint generated always as identity primary key,
    endpoint text not null check (endpoint in ('regional_forecast')),
    url text not null,
    fetched_at timestamptz not null,
    attempts smallint not null check (attempts >= 1),
    duration_ms integer not null check (duration_ms >= 0),
    http_status smallint,
    raw_gzip bytea,
    error text,
    -- A fetch that brought no body must say why.
    check (raw_gzip is not null or error is not null)
);

comment on table api_fetch is
'Each Carbon Intensity API call, kept even if it failed or did not parse.';

create table forecast_issue (
    feed text not null check (feed in ('regional')),
    area_id smallint not null check (area_id between 1 and 18),
    first_slot timestamptz not null,
    fetch_id bigint not null references api_fetch (fetch_id),
    intensities_g_per_kwh smallint[] not null check (
        cardinality(intensities_g_per_kwh) >= 1
        and array_position(intensities_g_per_kwh, null) is null
        and 0 <= all(intensities_g_per_kwh)
    ),
    primary key (feed, area_id, first_slot)
);

comment on table forecast_issue is
'An area''s forecast as first fetched. Its issue time is the fetch time.';
