// Pure parsing of a *verified* Stripe checkout.session.completed session into an
// entitlement grant. Returns null for anything that is not a clean, paid grant we
// recognise, so the caller never writes on malformed or ineligible data.

export interface Grant {
  userId: string;
  course: string;
  stripeRef: string;
}

interface SessionLike {
  id?: string | null;
  payment_status?: string | null;
  client_reference_id?: string | null;
  metadata?: { course?: string | null } | null;
}

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function parseCheckoutGrant(
  session: SessionLike,
  allowlist: readonly string[],
): Grant | null {
  if (!session || session.payment_status !== "paid") return null;
  const userId = session.client_reference_id ?? "";
  const course = session.metadata?.course ?? "";
  const stripeRef = session.id ?? "";
  if (!UUID_RE.test(userId)) return null;
  if (!allowlist.includes(course)) return null;
  if (!stripeRef) return null;
  return { userId, course, stripeRef };
}
