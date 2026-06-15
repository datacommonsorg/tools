'use client';

import {
  createContext,
  type ReactNode,
  useContext,
  useMemo,
  useState,
} from 'react';

interface ExportActionsContextProps {
  open(): void;
  close(): void;
  toggle(): void;
}

const ExportIsOpenContext = createContext<boolean>(false);
const ExportActionsContext = createContext<ExportActionsContextProps | null>(
  null,
);

interface ExportProviderProps {
  children: ReactNode;
}

export const ExportProvider = ({ children }: ExportProviderProps) => {
  const [isOpen, setIsOpen] = useState(false);

  // Keep the actions stable so consumers that only need them (e.g. cards on the
  // canvas) don't re-render when 'isOpen' changes
  const actions = useMemo<ExportActionsContextProps>(
    () => ({
      open: () => setIsOpen(true),
      close: () => setIsOpen(false),
      toggle: () => setIsOpen((isOpen) => !isOpen),
    }),
    [],
  );

  return (
    <ExportIsOpenContext.Provider value={isOpen}>
      <ExportActionsContext.Provider value={actions}>
        {children}
      </ExportActionsContext.Provider>
    </ExportIsOpenContext.Provider>
  );
};

/** Read whether the export panel is open — must be used inside `<ExportProvider>`. */
export const useExportIsOpen = (): boolean => useContext(ExportIsOpenContext);

/** Read the export actions — must be used inside `<ExportProvider>`. */
export const useExportActions = (): ExportActionsContextProps => {
  const context = useContext(ExportActionsContext);
  if (!context) {
    throw new Error("'useExportActions' must be used within 'ExportProvider'.");
  }

  return context;
};

/** Read the export state and actions together — re-renders when `isOpen` changes. */
export const useExport = () => {
  const isOpen = useExportIsOpen();
  const actions = useExportActions();

  return useMemo(() => ({ isOpen, ...actions }), [isOpen, actions]);
};
