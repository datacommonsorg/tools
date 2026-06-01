'use client';

import dynamic from 'next/dynamic';
import type { ChartDatum } from '~/components/elements/card/chart/data_line_chart';
import type { AtlasContent } from './atlas/helpers';

const Atlas = dynamic(
  () => import('./atlas/atlas').then((module) => module.Atlas),
  { ssr: false },
);

// Mock greenhouse-gas emissions (Mt CO₂e)
const MOCK_GHG_DATA: ChartDatum[] = [
  { year: 2000, emissions: 820 },
  { year: 2003, emissions: 905 },
  { year: 2006, emissions: 980 },
  { year: 2009, emissions: 1045 },
  { year: 2012, emissions: 1180 },
  { year: 2015, emissions: 1260 },
  { year: 2018, emissions: 1390 },
  { year: 2021, emissions: 1470 },
] as const;

// TODO: Drop once we have a real data source to feed initial content from
const DUMMY_CONTENT: AtlasContent[] = [
  {
    kind: 'card',
    title: 'Greenhouse gas emissions in Africa',
    isLoading: true,
  },
  {
    kind: 'card',
    title: 'Key insights when evaluating greenhouse gas emissions',
    body: 'Emissions per capita remain low relative to other regions, energy access is the dominant driver, and land-use change accounts for a large share of the total. missions per capita remain low relative to other regions, energy access is the dominant driver, and land-use change accounts for a large share of the total. missions per capita remain low relative to other regions, energy access is the dominant driver, and land-use change accounts for a large share of the total. missions per capita remain low relative to other regions, energy access is the dominant driver, and land-use change accounts for a large share of the total. missions per capita remain low relative to other regions, energy access is the dominant driver, and land-use change accounts for a large share of the total. missions per capita remain low relative to other regions, energy access is the dominant driver, and land-use change accounts for a large share of the total.',
  },
  {
    kind: 'card',
    title: 'Key insights when evaluating greenhouse gas emissions',
    body: 'Emissions per capita remain low relative to other regions, energy access is the dominant driver, and land-use change accounts for a large share of the total.',
  },
  {
    kind: 'card-chart',
    title: 'Greenhouse gas emissions in Africa',
    description:
      'The chart above tracks total GHG emissions across Africa over time.',
    data: MOCK_GHG_DATA,
  },
];

export const PageHome = () => {
  return <Atlas initialContent={DUMMY_CONTENT} />;
};
