'use client';

import { useEffect } from 'react';
import { useAtlas } from './atlas/use_atlas';

export const PageHome = () => {
  const atlas = useAtlas();

  // TODO: This is only temporary to show case adding / update flow
  useEffect(() => {
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

    return () => {
      clearTimeout(cardTimeout);
      clearTimeout(chartTimeout);
      cardText.remove();
      cardChart.remove();
    };
  }, [atlas]);

  return null;
};
