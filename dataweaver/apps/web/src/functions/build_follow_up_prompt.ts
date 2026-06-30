/**
 * Constructs a composite prompt when a user selects a followUp option,
 * combining the original query with the selected label so the model
 * has enough context to return actual data.
 */
export function buildFollowUpPrompt(
  originalQuery: string,
  selection: string,
): string {
  // Strategy 1: Concatenation
  return `${originalQuery}. ${selection}`;

  // // Strategy 2: Natural sentence
  // return `${originalQuery}, specifically ${selection}`;

  // // Strategy 3: Structured (keeps original and selection as distinct parts)
  // return `Original question: ${originalQuery}\nUser selected: ${selection}`;
}
