"use client";

import { useEffect, useState } from "react";

/** True after the first client paint — use to avoid SSR/client HTML mismatches. */
export function useClientMounted() {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  return mounted;
}
