'use client';

import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useRef,
} from 'react';
import { type Editor, Tldraw } from 'tldraw';
import s from './atlas.module.scss';
import { ATLAS_COMPONENTS, ATLAS_SHAPES } from './config';
import { type AtlasContent, contentToShape, gridPosition } from './helpers';

interface ContextValue {
  /** Push new content onto the atlas - auto-placed in the grid. */
  add: (content: AtlasContent) => void;
}

const AtlasContext = createContext<ContextValue | null>(null);

interface ProviderProps {
  /** Content placed onto the atlas when the editor first mounts. */
  initialContent?: AtlasContent[];
  children?: ReactNode;
}

export const Atlas = ({ initialContent = [], children }: ProviderProps) => {
  const hasPopulatedInitialContentRef = useRef(false);
  const editorRef = useRef<Editor | null>(null);

  // TODO: For now using count for positioning - we likely want to use a smarter
  // approach that accounts for deleted content and doesn't rely on order of
  // addition, etc later once we hook up to real data
  const countRef = useRef(0);

  const populate = useCallback((editor: Editor, content: AtlasContent) => {
    const shape = contentToShape(content, gridPosition(countRef.current));

    // If we don't get a shape back (e.g. unsupported content type) - skip it
    if (!shape) return;

    editor.createShape(shape);
    countRef.current += 1;
  }, []);

  const mounted = useCallback(
    (editor: Editor) => {
      editorRef.current = editor;

      // Render the dot grid (camera-tracked via the 'Grid' component slot)
      editor.updateInstanceState({ isGridMode: true });

      // Populate content (if we haven't already, e.g. due to fast refresh)
      if (!hasPopulatedInitialContentRef.current) {
        hasPopulatedInitialContentRef.current = true;
        for (const content of initialContent) populate(editor, content);
      }
    },
    [initialContent, populate],
  );

  const add = useCallback(
    (content: AtlasContent) => {
      const editor = editorRef.current;
      if (editor) populate(editor, content);
    },
    [populate],
  );

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

/** Hook for accessing the atlas context. */
export const useAtlas = () => {
  const value = useContext(AtlasContext);
  if (!value) throw new Error("'useAtlas' must be used within 'Atlas'.");
  return value;
};
