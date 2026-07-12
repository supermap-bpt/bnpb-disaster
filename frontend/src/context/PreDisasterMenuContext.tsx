import { createContext, useContext, useState, type ReactNode } from "react";

interface PreDisasterMenuContextValue {
  isOpen: boolean;
  setIsOpen: (open: boolean) => void;
}

const PreDisasterMenuContext = createContext<PreDisasterMenuContextValue | null>(null);

export function PreDisasterMenuProvider({ children }: { children: ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <PreDisasterMenuContext.Provider value={{ isOpen, setIsOpen }}>
      {children}
    </PreDisasterMenuContext.Provider>
  );
}

export function usePreDisasterMenu() {
  const ctx = useContext(PreDisasterMenuContext);
  if (ctx === null) {
    throw new Error("usePreDisasterMenu must be used within a PreDisasterMenuProvider");
  }
  return ctx;
}
