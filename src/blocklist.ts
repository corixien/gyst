// Domain rules: a domain matches itself, all subdomains and all paths.
export function normalizeDomain(input: string): string | null {
  let value = input.trim().toLowerCase();
  if (!value) return null;
  if (value.includes('://')) {
    try {
      value = new URL(value).hostname;
    } catch {
      return null;
    }
  }
  value = (value.split('/')[0] ?? '').replace(/^www\./, '').replace(/\.$/, '');
  if (!/^[a-z0-9-]+(\.[a-z0-9-]+)+$/.test(value)) return null;
  return value;
}

export function isBlockedUrl(url: string, domains: string[]): boolean {
  let hostname: string;
  try {
    hostname = new URL(url).hostname;
  } catch {
    return false;
  }
  return domains.some((domain) => hostname === domain || hostname.endsWith(`.${domain}`));
}
