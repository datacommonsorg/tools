import type { QuestionAndAnswers } from '~/components/scopes/page_home/follow_up';

export const MOCK_FOLLOW_UP: QuestionAndAnswers = {
  question: 'Do you know of a place in Africa called Seychelles?',
  answer:
    'Seychelles is a country in Africa. The population in Seychelles was ' +
    '121,354 in 2024. The nominal GDP per capita in Seychelles was ' +
    '$17,858.82 in 2024. The Gini index in Seychelles was 32.1 in 2018. ' +
    'The life expectancy in Seychelles was 74.96 in 2023. The energy ' +
    'consumption per capita in Seychelles was 2,410.83kgoe in 2007. The ' +
    'carbon dioxide emissions per capita in Seychelles was 7.24t in 2024.' +
    // TODO: Support HTML rendering here so that this line / future question
    // lines can support bold text
    '\n\nWhat specifically would you like to know?',
  prompts: [
    'Economic impact',
    'Health outcomes for its people',
    'Energy access in the country',
    'Environmental impact',
  ],
} as const;
