// The typed sentence may contain typos: one per 12 characters of the required sentence.
// Case counts as a typo, so "ich" for "Ich" is allowed but costs one of the typos.
const CHARS_PER_TYPO = 12;
// Length must match the sentence exactly, plus or minus one character (spaces and punctuation included).
const LENGTH_SLACK = 1;

export function allowedTypos(required: string): number {
  return Math.floor(required.length / CHARS_PER_TYPO);
}

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
  if (Math.abs(typed.length - required.length) > LENGTH_SLACK) return false;
  return editDistance(typed, required) <= allowedTypos(required);
}

// True while the input could still become the sentence; false once it is already too far off.
export function matchesSoFar(typed: string, required: string): boolean {
  if (typed.length > required.length + LENGTH_SLACK) return false;
  const prefix = required.slice(0, typed.length);
  return editDistance(typed, prefix) <= allowedTypos(required);
}
