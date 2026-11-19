do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'gridcast_reader') then
        create role gridcast_reader nologin;
    end if;
end
$$;

-- The API reads the newest issue and when it was fetched. It gets neither the
-- raw responses nor the error text, and cannot write.
grant usage on schema public to gridcast_reader;
grant select on forecast_issue to gridcast_reader;
grant select (fetch_id, fetched_at) on api_fetch to gridcast_reader;
