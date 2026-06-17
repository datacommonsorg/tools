'use client';

import {
  createContext,
  type ReactNode,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useAtlas } from '~/components/scopes/atlas/atlas_provider';
import { type MockQueryCleanup, runMockQuery } from '~/configs/mock_query';

export interface Status {
  promptValue: string;
  indicatorMessage: string;
}

interface QueryActionsContextProps {
  /** The current status of the query, if any. */
  status: Status | null;

  /** Run a query for the given prompt, streaming results onto the canvas. */
  runPrompt(prompt: string): void;

  /** Cancel the currently running prompt, if any. */
  cancelRunningPrompt(): void;
}

const QueryActionsContext = createContext<QueryActionsContextProps | null>(
  null,
);

interface QueryProviderProps {
  children: ReactNode;
}

export const QueryProvider = ({ children }: QueryProviderProps) => {
  const atlas = useAtlas();

  const [status, setStatus] = useState<Status | null>(null);

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
      status,
      runPrompt: (prompt: string) => {
        // TODO: Swap mock query for real query streaming setup here
        cleanupsRef.current.add(runMockQuery(prompt, atlas));

        // TODO: Hook up to real query status updates here
        setStatus({
          promptValue: prompt,
          indicatorMessage: 'Running query...',
        });
      },
      cancelRunningPrompt: () => {
        for (const cleanup of cleanupsRef.current) cleanup();
        cleanupsRef.current.clear();
        setStatus(null);
      },
    }),
    [atlas, status],
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
