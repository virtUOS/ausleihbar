// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { createContext, useContext, useState } from "react";
import type { ReactNode } from "react";

interface StartDateState {
  startDate: string | null; // YYYY-MM-DD, or null = no date chosen
  setStartDate: (date: string | null) => void;
}

const StartDateContext = createContext<StartDateState | undefined>(undefined);

/** Global "first lending day" chosen in the header; drives shop availability. */
export function StartDateProvider({ children }: { children: ReactNode }) {
  const [startDate, setStartDate] = useState<string | null>(null);
  return (
    <StartDateContext.Provider value={{ startDate, setStartDate }}>
      {children}
    </StartDateContext.Provider>
  );
}

export function useStartDate(): StartDateState {
  const ctx = useContext(StartDateContext);
  if (!ctx) throw new Error("useStartDate must be used within a StartDateProvider");
  return ctx;
}
