'use client';

import { COLORS } from '@package/tokens/ts';
import { type ReactNode, useCallback, useRef } from 'react';
import { createShapeId, type Editor, Tldraw } from 'tldraw';
import s from './atlas.module.scss';
import { ExportProvider } from './components/in_front_of_canvas/export/export_provider';
import { ATLAS_COMPONENTS, ATLAS_SHAPES, ZOOM_STEPS } from './config';
import { contentToShape, gridPosition } from './helpers';
import { type Atlas, AtlasContext } from './use_atlas';

type Operation = (editor: Editor) => void;

interface AtlasProviderProps {
  children: ReactNode;
}

export const AtlasProvider = ({ children }: AtlasProviderProps) => {
  const editorRef = useRef<Editor | null>(null);
  const pendingShapesQueueRef = useRef<((editor: Editor) => void)[]>([]);

  // TODO: For now using count for positioning - we likely want to use a smarter
  // approach that accounts for deleted content and doesn't rely on order of
  // addition, etc later once we hook up to real data
  const countRef = useRef(0);

  const withEditor = useCallback((operation: Operation) => {
    const editor = editorRef.current;

    // If we have the editor available - perform the operation immediately
    if (editor) operation(editor);
    // Otherwise queue it up for when the editor is ready (e.g. once mounted)
    else pendingShapesQueueRef.current.push(operation);
  }, []);

  const add: Atlas['add'] = useCallback(
    (content) => {
      const shapeId = createShapeId();

      // First: Create the shape with any immediately available content
      withEditor((e) => {
        e.createShape(
          contentToShape(shapeId, content, gridPosition(countRef.current)),
        );

        // Increment count for next shape's position
        countRef.current++;
      });

      // Then: Return handle that allows for future updates to the shape as more
      // content becomes available, or for the shape to be removed
      return {
        id: shapeId,
        variant: content.variant,
        update(props) {
          withEditor((e) =>
            e.updateShape({ id: shapeId, type: 'card', props }),
          );
        },
        remove() {
          withEditor((e) => e.deleteShapes([shapeId]));
        },
      };
    },
    [withEditor],
  );

  const mounted = useCallback((editor: Editor) => {
    // Render the dot grid (camera-tracked via the 'Grid' component slot)
    editor.updateInstanceState({ isGridMode: true });

    // Define camera zoom levels
    editor.setCameraOptions({ zoomSteps: [...ZOOM_STEPS] });

    // Style built-in theme to match our design system
    editor.updateThemes((themes) => {
      // Text styles
      themes.default.fonts.draw.fontFamily = '"Google Sans", sans-serif';
      themes.default.fontSize = 24;
      themes.default.lineHeight = 1.25;
      themes.default.colors.light.black.solid = `rgb(${COLORS['surface-content']})`;
      themes.default.colors.light.selectionStroke = `rgb(${COLORS['control-accent']})`;

      return themes;
    });

    editorRef.current = editor;
    countRef.current = 0;

    // If there were any operations queued up before the editor was ready,
    // run them now that we've mounted
    const queued = pendingShapesQueueRef.current;
    pendingShapesQueueRef.current = [];
    for (const operation of queued) operation(editor);
  }, []);

  return (
    <AtlasContext.Provider value={{ add }}>
      <ExportProvider>
        <Tldraw
          className={s.tldraw}
          hideUi
          components={ATLAS_COMPONENTS}
          shapeUtils={ATLAS_SHAPES}
          onMount={mounted}
        />
        {children}
      </ExportProvider>
    </AtlasContext.Provider>
  );
};
