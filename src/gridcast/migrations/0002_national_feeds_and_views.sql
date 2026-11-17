alter table api_fetch drop constraint api_fetch_endpoint_check;
alter table api_fetch add constraint api_fetch_endpoint_check check (
    endpoint in ('regional_forecast', 'national_forecast', 'national_actual')
);

alter table forecast_issue drop constraint forecast_issue_feed_check;
alter table forecast_issue add constraint forecast_issue_feed_check check (
    feed in ('regional', 'national')
);

create table national_actual (
    slot_start timestamptz primary key,
    intensity_g_per_kwh smallint check (intensity_g_per_kwh >= 0),
    -- The fetch that last changed this row.
    fetch_id bigint not null references api_fetch (fetch_id)
);

comment on table national_actual is
'Measured national intensity per half hour, null until NESO publishes it.';

create view forecast_value as
with unnested as (
    select
        issue.feed,
        issue.area_id,
        api_fetch.fetched_at as issued_at,
        step.intensity as intensity_g_per_kwh,
        issue.first_slot + (step.ordinal - 1) * interval '30 minutes'
            as slot_start
    from forecast_issue as issue
    inner join api_fetch on issue.fetch_id = api_fetch.fetch_id
    cross join
        lateral unnest(issue.intensities_g_per_kwh)
        with ordinality as step (intensity, ordinal)
)

select
    feed,
    area_id,
    issued_at,
    slot_start,
    intensity_g_per_kwh,
    -- Negative for the half hour under way when the forecast was fetched.
    cast(extract(epoch from slot_start - issued_at) / 60 as integer)
        as horizon_minutes
from unnested;

comment on view forecast_value is
'Each forecast intensity with its issue time and horizon in minutes.';

create view collection_coverage as
with recorded as (
    select distinct
        date_bin('30 minutes', fetched_at, timestamptz '2000-01-01 00:00+00')
            as half_hour
    from api_fetch
    where endpoint = 'regional_forecast' and error is null
)

select
    cast(half_hour at time zone 'UTC' as date) as day_utc,
    cast(count(*) as int) as half_hours_recorded,
    count(*) / 48.0 as share_recorded
from recorded
group by day_utc;

comment on view collection_coverage is
'Half hours with a regional forecast fetched, per UTC day. Today is partial.';

do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'gridcast_collector') then
        create role gridcast_collector nologin;
    end if;
end
$$;

grant usage on schema public to gridcast_collector;
grant select, insert on api_fetch, forecast_issue to gridcast_collector;
grant select, insert, update on national_actual to gridcast_collector;
grant select on forecast_value, collection_coverage to gridcast_collector;
