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
      relatedQueries: [
        'What are the key drivers of these trends?',
        'How does energy access compare across Africa?',
      ],
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
        { date: '2000', value: 928 },
        { date: '2003', value: 988 },
        { date: '2006', value: 1085 },
        { date: '2009', value: 1161 },
        { date: '2012', value: 1264 },
        { date: '2015', value: 1336 },
        { date: '2018', value: 1391 },
        { date: '2021', value: 1475 },
      ],
    },
  },
  {
    delay: 1500,
    content: {
      variant: 'text',
      title: 'Why European emissions have been falling',
      body: 'A sustained shift away from coal, strong efficiency standards, and rapid renewable deployment have driven emissions down even as the economy has continued to grow.',
      relatedQueries: [
        'Which policies drove the steepest cuts?',
        'How has renewable energy grown in Europe?',
      ],
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
        { date: '2000', value: 6156 },
        { date: '2003', value: 6391 },
        { date: '2006', value: 6529 },
        { date: '2009', value: 5893 },
        { date: '2012', value: 5999 },
        { date: '2015', value: 5613 },
        { date: '2018', value: 5614 },
        { date: '2021', value: 5265 },
      ],
      relatedQueries: ['How does this compare to other regions?'],
    },
  },
  {
    delay: 1500,
    content: {
      variant: 'text',
      title: 'What is driving emissions growth in Asia',
      body: 'Rapid industrialisation, rising energy demand, and continued reliance on coal have made the region the largest contributor to global emissions growth over the past two decades.',
      relatedQueries: [
        'How might this trajectory change?',
        'What is coal dependency in Asia?',
      ],
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
        { date: '2000', value: 9331 },
        { date: '2003', value: 11036 },
        { date: '2006', value: 13391 },
        { date: '2009', value: 15378 },
        { date: '2012', value: 18438 },
        { date: '2015', value: 19070 },
        { date: '2018', value: 20366 },
        { date: '2021', value: 21521 },
      ],
      relatedQueries: ['What would a lower-emissions pathway require?'],
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
