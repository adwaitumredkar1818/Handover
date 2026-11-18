"use client";

import React, { Suspense } from "react";
import { ConflictsWorkspace } from "../../../../components/verification/ConflictsWorkspace";

export default function ProjectConflictsPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-slate-100 animate-pulse" />}>
      <ConflictsWorkspace />
    </Suspense>
  );
}
