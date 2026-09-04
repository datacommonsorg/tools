import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import type { ChartSeries } from './chart';
import { getSeriesColor } from './palette';
import { TooltipCustom } from './tooltip_custom';

describe('TooltipCustom', () => {
  const singleSeries: ChartSeries[] = [
    {
      key: 'geoId/06',
      label: 'California',
      data: [{ date: '2020', value: 39538223 }],
    },
  ];

  const multiSeries: ChartSeries[] = [
    {
      key: 'geoId/06',
      label: 'California',
      data: [{ date: '2020', value: 39538223 }],
    },
    {
      key: 'geoId/48',
      label: 'Texas',
      data: [{ date: '2020', value: 29145505 }],
    },
  ];

  // Test: Inactive or empty tooltip
  // Situation: `active` is false or `payload` is empty.
  // Expectation: Renders nothing.
  it('returns null when inactive or payload is empty', () => {
    const htmlInactive = renderToStaticMarkup(
      <TooltipCustom
        active={false}
        payload={[{ value: 100, dataKey: 'value_0' }]}
        series={singleSeries}
      />,
    );
    expect(htmlInactive).toBe('');

    const htmlEmpty = renderToStaticMarkup(
      <TooltipCustom active={true} payload={[]} series={singleSeries} />,
    );
    expect(htmlEmpty).toBe('');
  });

  // Test: Single-series tooltip rendering
  // Situation: A chart with 1 series and a single payload entry.
  // Expectation: Renders formatted value and date label, without color swatch or series discriminator name.
  it('renders value and date without swatch or series discriminator in single-series mode', () => {
    const html = renderToStaticMarkup(
      <TooltipCustom
        active={true}
        payload={[{ value: 39538223, dataKey: 'value_0' }]}
        label="2020"
        series={singleSeries}
      />,
    );

    expect(html).toContain('39,538,223');
    expect(html).toContain('in 2020');
    expect(html).not.toContain('California');
    expect(html).not.toContain('style="background-color:');
  });

  // Test: Multi-series tooltip rendering
  // Situation: A chart with multiple series (e.g. California, Texas) and multiple payload entries.
  // Expectation: Renders color swatch, series discriminator name for each series, and formatted values.
  it('renders series discriminators and swatches when more than one series is present', () => {
    const html = renderToStaticMarkup(
      <TooltipCustom
        active={true}
        payload={[
          { value: 39538223, dataKey: 'value_0', name: 'California' },
          { value: 29145505, dataKey: 'value_1', name: 'Texas' },
        ]}
        label="2020"
        series={multiSeries}
      />,
    );

    expect(html).toContain('California');
    expect(html).toContain('Texas');
    expect(html).toContain('39,538,223');
    expect(html).toContain('29,145,505');
    expect(html).toContain(`background-color:${getSeriesColor(0)}`);
    expect(html).toContain(`background-color:${getSeriesColor(1)}`);
    expect(html).toContain('in 2020');
  });

  // Test: Fallback to series label when payload name is missing
  // Situation: Payload entry does not include `name`, but series has `label`.
  // Expectation: Discriminator name falls back to series label at that index.
  it('falls back to series.label if entry.name is absent', () => {
    const html = renderToStaticMarkup(
      <TooltipCustom
        active={true}
        payload={[
          { value: 39538223, dataKey: 'value_0' },
          { value: 29145505, dataKey: 'value_1' },
        ]}
        label="2020"
        series={multiSeries}
      />,
    );

    expect(html).toContain('California');
    expect(html).toContain('Texas');
  });

  // Test: Correct matching by series label independently of dataKey
  // Situation: Payload contains entry with name "Texas" and arbitrary dataKey.
  // Expectation: Correctly associates the entry with Texas series and its color.
  it('matches series by label independently of dataKey naming', () => {
    const html = renderToStaticMarkup(
      <TooltipCustom
        active={true}
        payload={[{ value: 29145505, dataKey: 'custom_key', name: 'Texas' }]}
        label="2020"
        series={multiSeries}
      />,
    );

    expect(html).toContain('Texas');
    expect(html).not.toContain('California');
    expect(html).toContain(`background-color:${getSeriesColor(1)}`);
  });

  // Test: Null value handling in multi-series tooltip
  // Situation: A series has null value for a given observation point.
  // Expectation: Renders "—" for the value while still displaying the series discriminator name and swatch.
  it('displays "—" for null or undefined values in multi-series mode', () => {
    const html = renderToStaticMarkup(
      <TooltipCustom
        active={true}
        payload={[
          { value: 39538223, dataKey: 'value_0', name: 'California' },
          { value: null, dataKey: 'value_1', name: 'Texas' },
        ]}
        label="2020"
        series={multiSeries}
      />,
    );

    expect(html).toContain('California');
    expect(html).toContain('39,538,223');
    expect(html).toContain('Texas');
    expect(html).toContain('—');
  });

  // Test: NaN value handling
  // Situation: An entry has NaN as its value.
  // Expectation: Renders "—" instead of the literal string "NaN".
  it('displays "—" when value is NaN instead of literal NaN string', () => {
    const html = renderToStaticMarkup(
      <TooltipCustom
        active={true}
        payload={[
          { value: Number.NaN, dataKey: 'value_0', name: 'California' },
        ]}
        label="2020"
        series={singleSeries}
      />,
    );

    expect(html).not.toContain('NaN');
    expect(html).toContain('—');
  });
});
