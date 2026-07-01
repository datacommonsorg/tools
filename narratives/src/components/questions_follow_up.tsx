/**
 * @fileoverview Follow-up questions block shown under an answer. Lists
 * clickable suggested questions (Figma node 3427-16785 heading + 3427-16786
 * body); selecting one re-submits it via the supplied `onAsk` callback.
 */

const COLOR_HEADING = "#1B1C1D";
const COLOR_LINK = "#175C75";
const FONT_STACK =
  '"Google Sans Text", "Google Sans", Inter, system-ui, sans-serif';

interface QuestionsFollowUpProps {
  questions: string[];
  onAsk?: (question: string) => void;
}

/**
 * Renders the list of follow-up question buttons. Returns nothing when there
 * are no questions to show.
 */
export function QuestionsFollowUp({
  questions,
  onAsk,
}: QuestionsFollowUpProps) {
  if (!questions || questions.length === 0) return null;

  return (
    <section aria-labelledby="followups-heading" className="mt-2">
      <h2
        id="followups-heading"
        className="font-medium"
        style={{
          fontFamily: '"Google Sans", "Google Sans Text", sans-serif',
          fontSize: 22,
          lineHeight: "28px",
          color: COLOR_HEADING,
          fontWeight: 500,
          margin: 0,
          paddingTop: 12,
        }}
      >
        Follow up questions
      </h2>
      <ul
        className="list-none p-0 m-0 mt-2 flex flex-col gap-1.5"
        style={{
          fontFamily: FONT_STACK,
          fontSize: 16,
          lineHeight: "24px",
          fontWeight: 500,
        }}
      >
        {questions.map((q, i) => (
          <li key={`${q}-${i}`}>
            <button
              type="button"
              onClick={() => onAsk?.(q)}
              className="bg-transparent border-0 p-0 text-left cursor-pointer hover:underline"
              style={{ color: COLOR_LINK, font: "inherit" }}
            >
              {q}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
