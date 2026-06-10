'use client';

import {
  createContext,
  type ReactNode,
  useContext,
  useMemo,
  useState,
} from 'react';

interface ExportContextProps {
  readonly isOpen: boolean;
  open(): void;
  close(): void;
  toggle(): void;
}

const ExportContext = createContext<ExportContextProps | null>(null);

interface ExportProviderProps {
  children: ReactNode;
}

export const ExportProvider = ({ children }: ExportProviderProps) => {
  const [isOpen, setIsOpen] = useState(false);

  const providerValue = useMemo<ExportContextProps>(
    () => ({
      isOpen,
      open: () => setIsOpen(true),
      close: () => setIsOpen(false),
      toggle: () => setIsOpen((isOpen) => !isOpen),
    }),
    [isOpen],
  );

  return (
    <ExportContext.Provider value={providerValue}>
      {children}
    </ExportContext.Provider>
  );
};

/** Read the export controls — must be used inside `<ExportProvider>`. */
export const useExport = (): ExportContextProps => {
  const context = useContext(ExportContext);
  if (!context) {
    throw new Error("'useExport' must be used within 'ExportProvider'.");
  }

  return context;
};
