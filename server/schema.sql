CREATE TABLE IF NOT EXISTS accounts (
  id uuid PRIMARY KEY,
  token_hash text NOT NULL UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS account_state (
  account_id uuid PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
  settings jsonb NOT NULL DEFAULT '{}'::jsonb,
  free_windows jsonb NOT NULL DEFAULT '[]'::jsonb,
  grant_until bigint NOT NULL DEFAULT 0,
  settings_until bigint NOT NULL DEFAULT 0,
  last_stamp bigint NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS partners (
  id uuid PRIMARY KEY,
  account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  pubkey text NOT NULL,
  name text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (account_id, pubkey)
);

CREATE TABLE IF NOT EXISTS invites (
  code_hash text PRIMARY KEY,
  account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  expires_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS grant_log (
  id bigserial PRIMARY KEY,
  account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  partner_id uuid REFERENCES partners(id) ON DELETE SET NULL,
  tier text NOT NULL,
  granted_at timestamptz NOT NULL DEFAULT now()
);
