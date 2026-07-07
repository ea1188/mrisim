-- Audit provenance on entitlements: how a grant was made and (for Stripe) which
-- checkout session produced it. Nullable/defaulted so it is backward compatible —
-- every existing manual grant reads as granted_via = 'manual'. Not read by any RLS
-- policy or gate; purely for audit and support. Apply after 0003.
alter table entitlements
  add column granted_via text not null default 'manual',
  add column stripe_ref  text;
