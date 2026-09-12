-- Apply before deploying the new WAS/frontend. Existing rows stay unverified (NULL).
-- Re-runnable MariaDB migration; no existing messages are deleted.
ALTER TABLE chat_message ADD COLUMN IF NOT EXISTS policy_version VARCHAR(16) NULL;
ALTER TABLE tarot_chat_message ADD COLUMN IF NOT EXISTS policy_version VARCHAR(16) NULL;
