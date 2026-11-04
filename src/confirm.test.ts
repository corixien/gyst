import { describe, expect, it } from 'vitest';
import { allowedTypos, matchesSentence } from './confirm';

const SENTENCE = 'Ich will das wirklich, auch wenn es weh tut.'; // 9 words, 2 punctuation marks, 44 chars -> 3 typos

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

  it('accepts a single extra or missing letter without breaking the word count', () => {
    expect(matchesSentence('Ich willl das wirklich, auch wenn es weh tut.', SENTENCE)).toBe(true);
    expect(matchesSentence('Ich wil das wirklich, auch wenn es weh tut.', SENTENCE)).toBe(true);
  });

  it('accepts a word count off by one', () => {
    expect(matchesSentence('Ich will das wirklich, auch wenn es weh tut zu.', SENTENCE)).toBe(true);
    expect(matchesSentence('Ich will das wirklich, auch wenn es weh tut', SENTENCE)).toBe(true);
  });

  it('rejects a word count off by more than one', () => {
    expect(matchesSentence('Ich will wirklich, auch es tut.', SENTENCE)).toBe(false);
    expect(matchesSentence('Ich will.', SENTENCE)).toBe(false);
  });

  it('rejects a punctuation count off by more than one', () => {
    expect(matchesSentence('Ich will das wirklich auch wenn es weh tut.', SENTENCE)).toBe(true);
    expect(matchesSentence('Ich will das wirklich auch wenn es weh tut', SENTENCE)).toBe(false);
    expect(matchesSentence('Ich will das wirklich, auch wenn es weh tut!!!!', SENTENCE)).toBe(false);
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
