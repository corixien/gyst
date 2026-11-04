// The typed sentence may contain typos: one per 12 characters of the required sentence.
// Case counts as a typo, so "ich" for "Ich" is allowed but costs one of the typos.
const CHARS_PER_TYPO = 12;
// Word and punctuation counts must match the sentence, plus or minus one.
const COUNT_SLACK = 1;

export function allowedTypos(required: string): number {
  return Math.floor(required.length / CHARS_PER_TYPO);
}

const countWords = (text: string) => text.trim().split(/\s+/).filter(Boolean).length;
const countPunctuation = (text: string) => (text.match(/\p{P}/gu) ?? []).length;

function editDistance(a: string, b: string): number {
  let previous = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    const current = [i];
    for (let j = 1; j <= b.length; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      current[j] = Math.min(previous[j]! + 1, current[j - 1]! + 1, previous[j - 1]! + cost);
    }
    previous = current;
  }
  return previous[b.length]!;
}

export function matchesSentence(typed: string, required: string): boolean {
  if (Math.abs(countWords(typed) - countWords(required)) > COUNT_SLACK) return false;
  if (Math.abs(countPunctuation(typed) - countPunctuation(required)) > COUNT_SLACK) return false;
  return editDistance(typed, required) <= allowedTypos(required);
}
