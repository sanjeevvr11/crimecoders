export const TierBadge = ({ tier }: { tier?: string | null }) =>
  tier ? <span className={`badge tier-${tier}`}>{tier}</span> : <span className="muted">—</span>;

export const RoleBadge = ({ role }: { role?: string | null }) =>
  role ? <span className={`badge role role-${role.replace(/[^a-z]/g, "")}`}>{role}</span> : <span className="muted">—</span>;

export const SourceTag = ({ source }: { source: string }) => <span className={`tag src-${source}`}>{source}</span>;
