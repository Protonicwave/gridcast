-- The accuracy endpoint compares archived forecasts with the measured
-- intensity. The reader sees the slot and the measurement, and not which
-- fetch last changed it.
grant select (slot_start, intensity_g_per_kwh)
on national_actual to gridcast_reader;
