import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { Tooltip, TooltipContent } from './tooltip';

describe('Tooltip', () => {
  // Test: Null render when children are absent
  // Situation: Tooltip rendered without any children.
  // Expectation: Returns null / empty markup.
  it('returns null when no children are provided', () => {
    const html = renderToStaticMarkup(<Tooltip />);
    expect(html).toBe('');
  });

  // Test: Static layout shell rendering
  // Situation: Tooltip rendered with children and without coords.
  // Expectation: Renders container div without coordinates style or floating class.
  it('renders children within tooltip shell when static', () => {
    const html = renderToStaticMarkup(
      <Tooltip>
        <div>Static Content</div>
      </Tooltip>,
    );

    expect(html).toContain('Static Content');
    expect(html).not.toContain('style=');
  });

  // Test: Floating positioning
  // Situation: Tooltip rendered with coordinates.
  // Expectation: Renders container div with inlined left and top style attributes.
  it('inlines left and top styles when coords are provided', () => {
    const html = renderToStaticMarkup(
      <Tooltip coords={{ x: 120, y: 80 }}>
        <div>Floating Content</div>
      </Tooltip>,
    );

    expect(html).toContain('Floating Content');
    expect(html).toContain('left:120px');
    expect(html).toContain('top:80px');
  });
});

describe('TooltipContent', () => {
  // Test: Null render when empty
  // Situation: TooltipContent rendered without title, items, emptyMessage, or children.
  // Expectation: Returns null / empty markup.
  it('returns null when there is no content to display', () => {
    const html = renderToStaticMarkup(<TooltipContent />);
    expect(html).toBe('');
  });

  // Test: Content rendering with title, items, subtitle, and hint
  // Situation: Standard chart content with items, title, and interaction hint.
  // Expectation: Formats values, renders title, series names, swatches, and hint.
  it('renders title, items, subtitle, and hint correctly', () => {
    const html = renderToStaticMarkup(
      <TooltipContent
        title="California"
        subtitle="in 2020"
        items={[
          {
            name: 'Population',
            value: 39538223,
            color: '#ff0000',
          },
        ]}
        hint="Click to view time series"
      />,
    );

    expect(html).toContain('California');
    expect(html).toContain('in 2020');
    expect(html).toContain('Population');
    expect(html).toContain('39,538,223');
    expect(html).toContain('background-color:#ff0000');
    expect(html).toContain('Click to view time series');
  });

  // Test: Empty message rendering
  // Situation: Value is unavailable and an emptyMessage is specified.
  // Expectation: Renders title and emptyMessage without crashing.
  it('renders emptyMessage when items are not present', () => {
    const html = renderToStaticMarkup(
      <TooltipContent title="Germany" emptyMessage="No data for 2020" />,
    );

    expect(html).toContain('Germany');
    expect(html).toContain('No data for 2020');
  });

  // Test: Null and NaN value formatting
  // Situation: TooltipContent receives null and NaN values.
  // Expectation: Formats both as an em dash "—".
  it('formats null and NaN values as an em dash', () => {
    const html = renderToStaticMarkup(
      <TooltipContent
        items={[
          { name: 'Missing Entry', value: null },
          { name: 'Invalid Entry', value: Number.NaN },
        ]}
      />,
    );

    expect(html).toContain('Missing Entry');
    expect(html).toContain('Invalid Entry');
    expect(html).not.toContain('NaN');
    expect(html).toContain('—');
  });
});
