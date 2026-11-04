// The typed sentence may contain typos: one per 12 characters of the required sentence.
const CHARS_PER_TYPO = 12;

const normalize = (text: string) => text.trim().toLowerCase();

export function allowedTypos(required: string): number {
  return Math.floor(normalize(required).length / CHARS_PER_TYPO);
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
  return editDistance(normalize(typed), normalize(required)) <= allowedTypos(required);
}

// True while the input could still become the sentence; false once it is already too far off.
export function matchesSoFar(typed: string, required: string): boolean {
  const value = normalize(typed);
  const prefix = normalize(required).slice(0, value.length);
  return editDistance(value, prefix) <= allowedTypos(required);
}
