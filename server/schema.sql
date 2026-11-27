-- Owners (accounts): settings and free time. Owners hold only device tokens, never a partner login.
CREATE TABLE IF NOT EXISTS accounts (
  id uuid PRIMARY KEY,
  created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE accounts DROP COLUMN IF EXISTS token_hash;

CREATE TABLE IF NOT EXISTS account_state (
  account_id uuid PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
  settings jsonb NOT NULL DEFAULT '{}'::jsonb,
  free_windows jsonb NOT NULL DEFAULT '[]'::jsonb,
  grant_until bigint NOT NULL DEFAULT 0,
  settings_until bigint NOT NULL DEFAULT 0
);

-- Device tokens of an owner's add-on. Created by claiming a code.
CREATE TABLE IF NOT EXISTS devices (
  token_hash text PRIMARY KEY,
  account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Partners: a username and a password. Usernames are unique.
CREATE TABLE IF NOT EXISTS partner_users (
  id uuid PRIMARY KEY,
  username text NOT NULL UNIQUE,
  pass_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS partner_sessions (
  token_hash text PRIMARY KEY,
  partner_id uuid NOT NULL REFERENCES partner_users(id) ON DELETE CASCADE,
  expires_at timestamptz NOT NULL
);

-- Which partner belongs to which owner.
CREATE TABLE IF NOT EXISTS links (
  account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  partner_id uuid NOT NULL REFERENCES partner_users(id) ON DELETE CASCADE,
  label text NOT NULL DEFAULT '',  -- name the partner gave this owner, only shown to that partner
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (account_id, partner_id)
);

-- Codes the owner's add-on claims together with the issuing partner's username.
CREATE TABLE IF NOT EXISTS claims (
  code_hash text PRIMARY KEY,
  account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  issuer_id uuid NOT NULL REFERENCES partner_users(id) ON DELETE CASCADE,
  expires_at timestamptz NOT NULL
);

-- Partner-to-partner pairing: an existing partner adds another partner to one owner; the new partner enters the code.
CREATE TABLE IF NOT EXISTS pairings (
  code_hash text PRIMARY KEY,
  account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  inviter_id uuid NOT NULL REFERENCES partner_users(id) ON DELETE CASCADE,
  invitee_id uuid NOT NULL REFERENCES partner_users(id) ON DELETE CASCADE,
  expires_at timestamptz NOT NULL
);
