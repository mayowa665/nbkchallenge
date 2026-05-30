-- ============================================================================
-- NBK League — Supabase schema
-- Paste this whole file into Supabase: SQL Editor -> New query -> Run.
-- Then set your shared PIN with the statement at the very bottom.
-- ============================================================================

-- pgcrypto gives us crypt()/gen_salt() for hashing the shared PIN.
create extension if not exists pgcrypto with schema extensions;

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------

-- One row holding the bcrypt hash of the shared group PIN.
create table if not exists public.app_config (
  id        int primary key default 1,
  pin_hash  text not null,
  constraint app_config_singleton check (id = 1)
);

-- Fixtures for the tracked teams in the window. Written by the GitHub Action
-- (service role). kickoff_utc is what enforces the prediction lock.
create table if not exists public.fixtures (
  id          int primary key,            -- football-data match id
  home        text not null,
  away        text not null,
  kickoff_utc timestamptz not null,
  home_score  int,
  away_score  int,
  status      text not null default 'SCHEDULED'
);

-- One prediction per player per fixture.
create table if not exists public.predictions (
  player      text not null,
  fixture_id  int  not null references public.fixtures(id) on delete cascade,
  home_pred   int  not null,
  away_pred   int  not null,
  updated_at  timestamptz not null default now(),
  primary key (player, fixture_id)
);

-- ---------------------------------------------------------------------------
-- Write path: the ONLY way to insert a prediction. Verifies the PIN and that
-- kickoff hasn't passed, server-side, so the lock can't be bypassed from the page.
-- ---------------------------------------------------------------------------
create or replace function public.submit_prediction(
  p_player     text,
  p_pin        text,
  p_fixture_id int,
  p_home       int,
  p_away       int
) returns text
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_hash    text;
  v_kickoff timestamptz;
begin
  if coalesce(trim(p_player), '') = '' then
    raise exception 'Pick a player';
  end if;

  select pin_hash into v_hash from public.app_config where id = 1;
  if v_hash is null or crypt(p_pin, v_hash) <> v_hash then
    raise exception 'Invalid PIN';
  end if;

  select kickoff_utc into v_kickoff from public.fixtures where id = p_fixture_id;
  if v_kickoff is null then
    raise exception 'Unknown fixture';
  end if;
  if now() >= v_kickoff then
    raise exception 'Predictions locked: kickoff has passed';
  end if;

  if p_home is null or p_away is null or p_home < 0 or p_away < 0 or p_home > 30 or p_away > 30 then
    raise exception 'Enter a valid score';
  end if;

  insert into public.predictions (player, fixture_id, home_pred, away_pred, updated_at)
  values (p_player, p_fixture_id, p_home, p_away, now())
  on conflict (player, fixture_id) do update
    set home_pred = excluded.home_pred,
        away_pred = excluded.away_pred,
        updated_at = now();

  return 'ok';
end;
$$;

-- Read path for the page: a player can see ONLY their own predictions (PIN-checked),
-- so nobody can scrape everyone's picks before kickoff. Picks for games that have
-- already kicked off are revealed publicly via state.json (built by the Action).
create or replace function public.my_predictions(
  p_player text,
  p_pin    text
) returns table (fixture_id int, home_pred int, away_pred int)
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_hash text;
begin
  select pin_hash into v_hash from public.app_config where id = 1;
  if v_hash is null or crypt(p_pin, v_hash) <> v_hash then
    raise exception 'Invalid PIN';
  end if;
  return query
    select pr.fixture_id, pr.home_pred, pr.away_pred
    from public.predictions pr
    where pr.player = p_player;
end;
$$;

-- ---------------------------------------------------------------------------
-- Row Level Security. anon may READ the fixture list (public schedule) and CALL the
-- two RPCs, but CANNOT read the predictions table directly (no select policy) — so
-- picks can't be scraped before kickoff. The Action uses the service role, which
-- bypasses RLS, to read all predictions and write fixtures.
-- ---------------------------------------------------------------------------
alter table public.fixtures    enable row level security;
alter table public.predictions enable row level security;

drop policy if exists "read fixtures" on public.fixtures;
create policy "read fixtures" on public.fixtures for select using (true);
-- (intentionally no select policy on predictions)

grant select on public.fixtures to anon;
grant execute on function public.submit_prediction(text, text, int, int, int) to anon;
grant execute on function public.my_predictions(text, text) to anon;

-- ---------------------------------------------------------------------------
-- FINAL STEP — set your shared PIN (change 'changeme' to your chosen PIN):
--   insert into public.app_config (id, pin_hash)
--   values (1, extensions.crypt('changeme', extensions.gen_salt('bf')))
--   on conflict (id) do update set pin_hash = excluded.pin_hash;
-- ---------------------------------------------------------------------------
