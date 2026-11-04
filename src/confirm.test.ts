import { describe, expect, it } from 'vitest';
import { allowedTypos, matchesSentence, matchesSoFar } from './confirm';

const SENTENCE = 'Ich will das wirklich, auch wenn es weh tut.'; // 44 chars -> 3 typos

describe('allowedTypos', () => {
  it('allows one typo per 12 characters', () => {
    expect(allowedTypos('short')).toBe(0);
    expect(allowedTypos('Ich will das wirklich.')).toBe(1);
    expect(allowedTypos(SENTENCE)).toBe(3);
  });
});

describe('matchesSentence', () => {
  it('accepts the exact sentence', () => {
    expect(matchesSentence(SENTENCE, SENTENCE)).toBe(true);
  });

  it('accepts typos within the allowance, same length', () => {
    expect(matchesSentence('Ich wil das wirklich, auch wenn es weh tot.', SENTENCE)).toBe(true);
  });

  it('accepts a length off by one', () => {
    expect(matchesSentence('Ich will das wirklich, auch wenn es weh tut', SENTENCE)).toBe(true);
    expect(matchesSentence('Ich will das wirklich, auch wenn es weh tut..', SENTENCE)).toBe(true);
  });

  it('rejects a length off by more than one, even with correct characters', () => {
    expect(matchesSentence('Ich will das wirklich, auch wenn es weh tu', SENTENCE)).toBe(false);
    expect(matchesSentence('Ich will das wirklich, auch wenn es weh tut...', SENTENCE)).toBe(false);
    expect(matchesSentence('Ichwill das wirklich, auch wenn es weh tut.', SENTENCE)).toBe(true);
    expect(matchesSentence('Ichwilldaswirklich,auchwennesweh tut.', SENTENCE)).toBe(false);
  });

  it('counts case as a typo', () => {
    expect(matchesSentence('ich will das wirklich, auch wenn es weh tut.', SENTENCE)).toBe(true);
    expect(matchesSentence('ich WILL das Wirklich, auch wenn es weh tut.', SENTENCE)).toBe(false);
  });

  it('rejects more typos than allowed', () => {
    expect(matchesSentence('Ich wil das wirklch, auch wen es weh tt.', SENTENCE)).toBe(false);
  });

  it('requires exact text for short sentences', () => {
    expect(matchesSentence('Ich will', 'Ich will')).toBe(true);
    expect(matchesSentence('Ich wil', 'Ich will')).toBe(false);
  });
});

describe('matchesSoFar', () => {
  it('stays true while the typed prefix is still close enough', () => {
    expect(matchesSoFar('', SENTENCE)).toBe(true);
    expect(matchesSoFar('Ich wil', SENTENCE)).toBe(true);
    expect(matchesSoFar('Ich will das wirklich, auch', SENTENCE)).toBe(true);
  });

  it('turns false once the input is clearly off or too long', () => {
    expect(matchesSoFar('Qwertzuiop', SENTENCE)).toBe(false);
    expect(matchesSoFar(SENTENCE + '!!', SENTENCE)).toBe(false);
  });
});
