import { describe, expect, it } from 'vitest';
import { buildBlockRules, normalizeDomain } from './blocklist';

describe('normalizeDomain', () => {
  it('accepts plain domains and URLs', () => {
    expect(normalizeDomain('YouTube.com')).toBe('youtube.com');
    expect(normalizeDomain('https://www.reddit.com/r/all?x=1')).toBe('reddit.com');
    expect(normalizeDomain('  m.youtube.com/watch  ')).toBe('m.youtube.com');
  });

  it('rejects empty and invalid input', () => {
    expect(normalizeDomain('')).toBeNull();
    expect(normalizeDomain('localhost')).toBeNull();
    expect(normalizeDomain('not a domain')).toBeNull();
    expect(normalizeDomain('https://[bad')).toBeNull();
  });
});

describe('buildBlockRules', () => {
  it('builds one redirect rule per domain with subdomain and path matching', () => {
    const rules = buildBlockRules(['youtube.com', 'reddit.com'], '/blocked.html');
    expect(rules).toEqual([
      {
        id: 1,
        priority: 1,
        action: { type: 'redirect', redirect: { extensionPath: '/blocked.html' } },
        condition: { urlFilter: '||youtube.com^', resourceTypes: ['main_frame'] },
      },
      {
        id: 2,
        priority: 1,
        action: { type: 'redirect', redirect: { extensionPath: '/blocked.html' } },
        condition: { urlFilter: '||reddit.com^', resourceTypes: ['main_frame'] },
      },
    ]);
  });
});
