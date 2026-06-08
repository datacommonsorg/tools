'use client';

import { AnimatePresence } from 'motion/react';
import { useEffect, useRef, useState } from 'react';
import { useAtlas } from '~/components/scopes/atlas/use_atlas';
import { Intro } from './intro';
import s from './page_home.module.scss';
import { Prompt } from './prompt';

export const PageHome = () => {
  const atlas = useAtlas();

  const timeoutsRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  const [isIntroVisible, setIsIntroVisible] = useState(true);
  const [query, setQuery] = useState('');

  useEffect(() => {
    return () => {
      // Clear any in-flight timeouts if the page unmounts mid-response
      for (const timeout of timeoutsRef.current) clearTimeout(timeout);
    };
  }, []);

  // TODO: This is entirely using mock data for now
  const runMockQuery = () => {
    const cardText = atlas.add({
      variant: 'text',
      title: 'Key insights when evaluating greenhouse gas emissions',
      isLoading: true,
    });

    const cardChart = atlas.add({
      variant: 'chart',
      title: 'Greenhouse gas emissions in Africa',
      isLoading: true,
    });

    // Populate them as 'data arrives'
    const cardTimeout = setTimeout(() => {
      cardText.update({
        body: 'Emissions per capita remain low relative to other regions, energy access is the dominant driver, and land-use change accounts for a large share of the total.',
        isLoading: false,
        followUp: 'What are the key drivers of these trends?',
      });
    }, 1500);

    const chartTimeout = setTimeout(() => {
      cardChart.update({
        description:
          'The chart above tracks total GHG emissions across Africa over time.',
        data: [
          { year: 2000, emissions: 820 },
          { year: 2003, emissions: 905 },
          { year: 2006, emissions: 980 },
          { year: 2009, emissions: 1045 },
          { year: 2012, emissions: 1180 },
          { year: 2015, emissions: 1260 },
          { year: 2018, emissions: 1390 },
          { year: 2021, emissions: 1470 },
        ],
        isLoading: false,
        followUp: 'What are the key drivers of these trends?',
      });
    }, 2500);

    timeoutsRef.current.push(cardTimeout, chartTimeout);
  };

  return (
    <div className={s.container}>
      <AnimatePresence>
        {isIntroVisible && (
          <Intro onSelect={setQuery} onClose={() => setIsIntroVisible(false)} />
        )}
      </AnimatePresence>

      <Prompt
        value={query}
        onValueChange={setQuery}
        onSubmit={() => {
          runMockQuery();
          setQuery('');
          setIsIntroVisible(false);
        }}
      />
    </div>
  );
};
