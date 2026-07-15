const PUNCTUATION = /[^\w\s]/g;
const WHITESPACE = /\s+/g;

function tokenize(str: string): Set<string> {
  const normalized = str
    .toLowerCase()
    .trim()
    .replace(PUNCTUATION, '')
    .replace(WHITESPACE, ' ');
  return new Set(normalized.split(' ').filter(Boolean));
}

function jaccard(a: Set<string>, b: Set<string>): number {
  let intersection = 0;
  for (const token of a) {
    if (b.has(token)) intersection++;
  }
  const union = a.size + b.size - intersection;
  return union === 0 ? 1 : intersection / union;
}

export const deduplicateStrings = (
  items: string[],
  threshold = 0.7,
): string[] => {
  const accepted: Array<{ original: string; tokens: Set<string> }> = [];

  for (const item of items) {
    const tokens = tokenize(item);
    const isDuplicate = accepted.some(
      (entry) => jaccard(entry.tokens, tokens) >= threshold,
    );
    if (!isDuplicate) {
      accepted.push({ original: item, tokens });
    }
  }

  return accepted.map((entry) => entry.original);
};
