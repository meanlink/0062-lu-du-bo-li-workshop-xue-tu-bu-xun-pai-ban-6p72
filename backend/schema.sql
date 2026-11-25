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
 starts_at timestamptz NOT NULL, capacity smallint NOT NULL CHECK (capacity > 0), instructor text NOT NULL,
 closed boolean NOT NULL DEFAULT false,
 closed_at timestamptz, closed_by text, closed_reason text
);
ALTER TABLE coaching_slots ADD COLUMN IF NOT EXISTS closed boolean NOT NULL DEFAULT false;
ALTER TABLE coaching_slots ADD COLUMN IF NOT EXISTS closed_at timestamptz;
ALTER TABLE coaching_slots ADD COLUMN IF NOT EXISTS closed_by text;
ALTER TABLE coaching_slots ADD COLUMN IF NOT EXISTS closed_reason text;
CREATE TABLE IF NOT EXISTS coaching_assignments (
 apprentice text PRIMARY KEY REFERENCES apprentices(code), slot text NOT NULL REFERENCES coaching_slots(code),
 recommended text NOT NULL CHECK (recommended IN ('bench','handoff','ready')),
 signed_by text NOT NULL, assigned_at timestamptz NOT NULL DEFAULT now(),
 origin_slot text REFERENCES coaching_slots(code),
 origin_signed_by text, origin_assigned_at timestamptz
);
ALTER TABLE coaching_assignments ADD COLUMN IF NOT EXISTS origin_slot text REFERENCES coaching_slots(code);
ALTER TABLE coaching_assignments ADD COLUMN IF NOT EXISTS origin_signed_by text;
ALTER TABLE coaching_assignments ADD COLUMN IF NOT EXISTS origin_assigned_at timestamptz;
UPDATE coaching_assignments SET origin_slot=slot, origin_signed_by=signed_by, origin_assigned_at=assigned_at
 WHERE origin_slot IS NULL;
-- 停课后未能迁出的学徒：保留原签核依据，等待后续班次撤席补位
CREATE TABLE IF NOT EXISTS coaching_makeup (
 apprentice text PRIMARY KEY REFERENCES apprentices(code),
 discipline text NOT NULL CHECK (discipline IN ('bench','handoff','ready')),
 origin_slot text NOT NULL REFERENCES coaching_slots(code),
 origin_signed_by text NOT NULL, origin_assigned_at timestamptz NOT NULL,
 queued_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS apprentice_profiles (
 apprentice text PRIMARY KEY REFERENCES apprentices(code), computed_at timestamptz NOT NULL DEFAULT now(),
 discipline text NOT NULL CHECK (discipline IN ('bench','handoff','ready')), n_distinct integer NOT NULL,
 margin real NOT NULL CHECK (margin >= 0), drivers jsonb NOT NULL, observation text NOT NULL REFERENCES skill_observations(code)
);
