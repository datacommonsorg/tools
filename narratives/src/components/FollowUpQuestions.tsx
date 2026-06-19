// Figma node 3427-16785 (heading "Follow up questions") + 3427-16786
// (text block listing three suggestions, each in #175C75, body-large-
// emphasized 16/24). Each suggestion is clickable — selecting it
// re-submits the question via the supplied onAsk callback.

const COLOR_HEADING = "#1B1C1D";
const COLOR_LINK = "#175C75";
const FONT_STACK =
  '"Google Sans Text", "Google Sans", Inter, system-ui, sans-serif';

interface FollowUpQuestionsProps {
  questions: string[];
  onAsk?: (question: string) => void;
}

export default function FollowUpQuestions({
  questions,
  onAsk,
}: FollowUpQuestionsProps) {
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
