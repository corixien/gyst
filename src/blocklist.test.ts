import { describe, expect, it } from 'vitest';
import { isBlockedUrl, normalizeDomain } from './blocklist';

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

describe('isBlockedUrl', () => {
  it('matches the domain, its subdomains and all paths', () => {
    expect(isBlockedUrl('https://youtube.com/watch?v=1', ['youtube.com'])).toBe(true);
    expect(isBlockedUrl('https://m.youtube.com/', ['youtube.com'])).toBe(true);
    expect(isBlockedUrl('http://www.youtube.com/a/b', ['youtube.com'])).toBe(true);
  });

  it('does not match other domains or lookalikes', () => {
    expect(isBlockedUrl('https://notyoutube.com/', ['youtube.com'])).toBe(false);
    expect(isBlockedUrl('https://example.org/youtube.com', ['youtube.com'])).toBe(false);
    expect(isBlockedUrl('chrome://extensions', ['youtube.com'])).toBe(false);
  });
});
