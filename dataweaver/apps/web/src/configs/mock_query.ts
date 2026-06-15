import type { AtlasContextProps } from '~/components/scopes/atlas/atlas_provider';
import type { AtlasContent } from '~/components/scopes/atlas/helpers';

/** The slice of the atlas the mock needs — just the ability to add cards. */
type MockAtlas = Pick<AtlasContextProps, 'add'>;

/** A canned query result: the single card a query resolves to. */
interface MockResponse {
  /** ms after the query starts when the card's data 'arrives'. */
  delay: number;

  /** The fully-populated content the card resolves to. */
  content: AtlasContent;
}

const MOCK_RESPONSES: MockResponse[] = [
  {
    delay: 10000,
    content: {
      variant: 'text',
      title: 'Key insights when evaluating greenhouse gas emissions',
      body: 'Emissions per capita remain low relative to other regions, energy access is the dominant driver, and land-use change accounts for a large share of the total.',
      followUp: 'What are the key drivers of these trends?',
    },
  },
  {
    delay: 2500,
    content: {
      variant: 'chart',
      title: 'CO₂ emissions in Africa',
      description:
        'Annual CO₂ emissions from fossil fuels and industry across Africa, in million tonnes.',
      data: [
        { year: 2000, emissions: 928 },
        { year: 2003, emissions: 988 },
        { year: 2006, emissions: 1085 },
        { year: 2009, emissions: 1161 },
        { year: 2012, emissions: 1264 },
        { year: 2015, emissions: 1336 },
        { year: 2018, emissions: 1391 },
        { year: 2021, emissions: 1475 },
      ],
    },
  },
  {
    delay: 1500,
    content: {
      variant: 'text',
      title: 'Why European emissions have been falling',
      body: 'A sustained shift away from coal, strong efficiency standards, and rapid renewable deployment have driven emissions down even as the economy has continued to grow.',
      followUp: 'Which policies drove the steepest cuts?',
    },
  },
  {
    delay: 2500,
    content: {
      variant: 'chart',
      title: 'CO₂ emissions in Europe',
      description:
        'Annual CO₂ emissions from fossil fuels and industry across Europe, in million tonnes.',
      data: [
        { year: 2000, emissions: 6156 },
        { year: 2003, emissions: 6391 },
        { year: 2006, emissions: 6529 },
        { year: 2009, emissions: 5893 },
        { year: 2012, emissions: 5999 },
        { year: 2015, emissions: 5613 },
        { year: 2018, emissions: 5614 },
        { year: 2021, emissions: 5265 },
      ],
      followUp: 'How does this compare to other regions?',
    },
  },
  {
    delay: 1500,
    content: {
      variant: 'text',
      title: 'What is driving emissions growth in Asia',
      body: 'Rapid industrialisation, rising energy demand, and continued reliance on coal have made the region the largest contributor to global emissions growth over the past two decades.',
      followUp: 'How might this trajectory change?',
    },
  },
  {
    delay: 2500,
    content: {
      variant: 'chart',
      title: 'CO₂ emissions in Asia',
      description:
        'Annual CO₂ emissions from fossil fuels and industry across Asia, in million tonnes.',
      data: [
        { year: 2000, emissions: 9331 },
        { year: 2003, emissions: 11036 },
        { year: 2006, emissions: 13391 },
        { year: 2009, emissions: 15378 },
        { year: 2012, emissions: 18438 },
        { year: 2015, emissions: 19070 },
        { year: 2018, emissions: 20366 },
        { year: 2021, emissions: 21521 },
      ],
      followUp: 'What would a lower-emissions pathway require?',
    },
  },
];

export type MockQueryCleanup = () => void;

/**
 * Simulates a streaming query response using static data: a response is picked
 * at random, its cards are created in a loading state, then populated on a
 * delay to mimic data arriving over the wire. Returns a cleanup that cancels
 * any still-pending updates.
 *
 * TODO: Remove once `runPrompt` is backed by the real streaming query.
 */
export const runMockQuery = (
  _prompt: string,
  atlas: MockAtlas,
): MockQueryCleanup => {
  const timeouts: ReturnType<typeof setTimeout>[] = [];

  const cleanup = () => {
    for (const timeout of timeouts) clearTimeout(timeout);
  };

  const randomIndex = Math.floor(Math.random() * MOCK_RESPONSES.length);
  const randomResponse = MOCK_RESPONSES[randomIndex];
  if (!randomResponse) return cleanup;

  // Show the card immediately in a loading state, then reveal its content once
  // the data 'arrives'. The follow-up is withheld until loading ends, so it
  // only appears alongside the resolved content.
  const { delay, content } = randomResponse;
  const { variant, title, ...contentRest } = content;
  const card = atlas.add({ variant, title, isLoading: true });

  timeouts.push(
    setTimeout(() => card.update({ isLoading: false, ...contentRest }), delay),
  );

  return cleanup;
};
