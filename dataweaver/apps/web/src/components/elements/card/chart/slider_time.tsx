'use client';

import { type ChangeEvent, useEffect, useRef, useState } from 'react';
import { IconPause } from '~/components/primitives/icons/pause';
import { IconPlay } from '~/components/primitives/icons/play';
import s from './slider_time.module.scss';

export interface SliderTimeProps {
  dates: string[];
  selectedDate: string;
  onSelectDate: (date: string) => void;
}

export const SliderTime = ({
  dates,
  selectedDate,
  onSelectDate,
}: SliderTimeProps) => {
  const [isPlaying, setIsPlaying] = useState(false);

  const datesRef = useRef(dates);
  datesRef.current = dates;
  const onSelectDateRef = useRef(onSelectDate);
  onSelectDateRef.current = onSelectDate;
  const selectedDateRef = useRef(selectedDate);
  selectedDateRef.current = selectedDate;

  const currentIndex = Math.max(0, dates.indexOf(selectedDate));

  useEffect(() => {
    if (!isPlaying) return;

    const timer = setInterval(() => {
      const d = datesRef.current;
      if (d.length === 0) return;
      const currentIdx = Math.max(0, d.indexOf(selectedDateRef.current));
      const nextDate = d[(currentIdx + 1) % d.length];
      if (nextDate) {
        onSelectDateRef.current(nextDate);
      }
    }, 600);

    return () => clearInterval(timer);
  }, [isPlaying]);

  if (dates.length <= 1) {
    return null;
  }

  const handleSliderChange = (e: ChangeEvent<HTMLInputElement>) => {
    const nextIndex = Number.parseInt(e.target.value, 10);
    const date = dates[nextIndex];
    if (date) {
      onSelectDate(date);
    }
  };

  return (
    <div className={s.container}>
      <button
        type="button"
        className={s['button-play']}
        onClick={() => setIsPlaying((p) => !p)}
        aria-label={isPlaying ? 'Pause animation' : 'Play time animation'}
      >
        {isPlaying ? <IconPause /> : <IconPlay />}
      </button>

      <div className={s['slider-container']}>
        <div className={s['slider-track']}>
          <input
            type="range"
            className={s.slider}
            min={0}
            max={dates.length - 1}
            value={currentIndex}
            onChange={handleSliderChange}
            aria-label="Select year or date"
            aria-valuetext={selectedDate}
          />
        </div>
        <div className={s['labels-row']}>
          <span>{dates[0]}</span>
          <span>{dates[dates.length - 1]}</span>
        </div>
      </div>

      <span className={s['badge-date']}>{selectedDate}</span>
    </div>
  );
};
