'use client';

import { type ReactNode, useCallback, useRef } from 'react';
import { createShapeId, type Editor, type TLComponents, Tldraw } from 'tldraw';
import s from './atlas.module.scss';
import { Grid } from './components/grid';
import { contentToShape, gridPosition } from './helpers';
import { ShapeCardUtil } from './shapes/card';
import { type Atlas, AtlasContext } from './use_atlas';

const ATLAS_COMPONENTS = { Grid } as const satisfies TLComponents;

const ATLAS_SHAPES = [ShapeCardUtil] as const;

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
      <Tldraw
        className={s.tldraw}
        hideUi
        components={ATLAS_COMPONENTS}
        shapeUtils={ATLAS_SHAPES}
        onMount={mounted}
      />
      {children}
    </AtlasContext.Provider>
  );
};
