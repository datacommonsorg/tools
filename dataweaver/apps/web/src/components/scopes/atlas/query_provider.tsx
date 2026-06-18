'use client';

import {
  createContext,
  type ReactNode,
  useContext,
  useEffect,
  useMemo,
  useRef,
} from 'react';
import { useAtlas } from '~/components/scopes/atlas/atlas_provider';
import { type MockQueryCleanup, runMockQuery } from '~/configs/mock_query';

interface QueryActionsContextProps {
  /** Run a query for the given prompt, streaming results onto the canvas. */
  runPrompt(prompt: string): void;
}

const QueryActionsContext = createContext<QueryActionsContextProps | null>(
  null,
);

interface QueryProviderProps {
  children: ReactNode;
}

export const QueryProvider = ({ children }: QueryProviderProps) => {
  const atlas = useAtlas();

  const cleanupsRef = useRef<Set<MockQueryCleanup>>(new Set());

  useEffect(() => {
    const cleanups = cleanupsRef.current;
    return () => {
      for (const cleanup of cleanups) cleanup();
      cleanups.clear();
    };
  }, []);

  const providerValue = useMemo<QueryActionsContextProps>(
    () => ({
      runPrompt: (prompt: string) => {
        // TODO: Swap mock query for real query streaming setup here
        cleanupsRef.current.add(runMockQuery(prompt, atlas));
      },
    }),
    [atlas],
  );

  return (
    <QueryActionsContext.Provider value={providerValue}>
      {children}
    </QueryActionsContext.Provider>
  );
};

/** Read the query actions — must be used inside `<QueryProvider>`. */
export const useQueryActions = (): QueryActionsContextProps => {
  const context = useContext(QueryActionsContext);
  if (!context) {
    throw new Error("'useQueryActions' must be used within 'QueryProvider'.");
  }

  return context;
};
