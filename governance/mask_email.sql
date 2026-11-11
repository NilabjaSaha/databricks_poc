-- Column mask for email addresses.
-- Admins see the real value; everyone else sees the first letter and the domain.
-- {catalog} is replaced per environment by scripts/apply_governance.py.
CREATE OR REPLACE FUNCTION {catalog}.governance.mask_email(email STRING)
  RETURNS STRING
  COMMENT 'PII mask: full email for admins, n***@domain for others'
  RETURN CASE
    WHEN is_member('admins') THEN email
    ELSE concat(left(email, 1), '***@', split_part(email, '@', 2))
  END;