CREATE TABLE IF NOT EXISTS apprentices (
 code text PRIMARY KEY, name text NOT NULL, cohort text NOT NULL, mentor text NOT NULL,
 eligible boolean NOT NULL DEFAULT true, joined_on date NOT NULL
);
CREATE TABLE IF NOT EXISTS skill_observations (
 code text PRIMARY KEY, apprentice text REFERENCES apprentices(code), noted_on date NOT NULL,
 setup smallint NOT NULL CHECK (setup BETWEEN 0 AND 10),
 handoff smallint NOT NULL CHECK (handoff BETWEEN 0 AND 10),
 teardown smallint NOT NULL CHECK (teardown BETWEEN 0 AND 10),
 source text NOT NULL, label text CHECK (label IN ('bench','handoff','ready')),
 CHECK (apprentice IS NOT NULL OR label IS NOT NULL)
);
CREATE TABLE IF NOT EXISTS coaching_slots (
 code text PRIMARY KEY, discipline text NOT NULL CHECK (discipline IN ('bench','handoff','ready')),
 starts_at timestamptz NOT NULL, capacity smallint NOT NULL CHECK (capacity > 0), instructor text NOT NULL
);
CREATE TABLE IF NOT EXISTS coaching_assignments (
 apprentice text PRIMARY KEY REFERENCES apprentices(code), slot text NOT NULL REFERENCES coaching_slots(code),
 recommended text NOT NULL CHECK (recommended IN ('bench','handoff','ready')),
 signed_by text NOT NULL, assigned_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS apprentice_profiles (
 apprentice text PRIMARY KEY REFERENCES apprentices(code), computed_at timestamptz NOT NULL DEFAULT now(),
 discipline text NOT NULL CHECK (discipline IN ('bench','handoff','ready')), n_distinct integer NOT NULL,
 margin real NOT NULL CHECK (margin >= 0), drivers jsonb NOT NULL, observation text NOT NULL REFERENCES skill_observations(code)
);
