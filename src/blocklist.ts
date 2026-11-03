// Domain rules: "||example.com^" matches example.com, all subdomains and all paths.
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

export interface BlockRule {
  id: number;
  priority: number;
  action: { type: 'redirect'; redirect: { extensionPath: string } };
  condition: { urlFilter: string; resourceTypes: string[] };
}

export function buildBlockRules(domains: string[], blockPagePath: string): BlockRule[] {
  return domains.map((domain, index) => ({
    id: index + 1,
    priority: 1,
    action: { type: 'redirect', redirect: { extensionPath: blockPagePath } },
    condition: { urlFilter: `||${domain}^`, resourceTypes: ['main_frame'] },
  }));
}
