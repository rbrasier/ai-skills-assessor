-- v1_0_0_site_config
-- Add extensible JSONB settings column to the admin_settings singleton row.
-- Stores runtime-mutable site configuration (e.g. enable_sfia_flow) so
-- changes survive service restarts without requiring an .env redeploy.

ALTER TABLE admin_settings
  ADD COLUMN IF NOT EXISTS "siteConfig" JSONB NOT NULL DEFAULT '{}';
