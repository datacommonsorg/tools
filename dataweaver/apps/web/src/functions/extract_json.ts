/**
 * Extracts and parses the first JSON object found in a string. Useful for
 * pulling structured data from LLM responses that may contain surrounding
 * markdown or prose.
 *
 * Returns the parsed value on success, or `undefined` if no valid JSON object
 * is found.
 *
 * @example
 * extractJson('Here is the result: {"a": 1}'); // { a: 1 }
 * extractJson('no json here'); // undefined
 */
export const extractJson = <T = unknown>(text: string): T | undefined => {
  const match = text.match(/\{[\s\S]*\}/);
  if (!match) return undefined;

  try {
    return JSON.parse(match[0]) as T;
  } catch {
    return undefined;
  }
};
