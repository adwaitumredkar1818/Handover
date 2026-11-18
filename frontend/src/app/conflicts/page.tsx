"use client";

import React, { Suspense } from "react";
import { ConflictManagementWorkspace } from "../../components/conflicts/ConflictManagementWorkspace";

export default function ConflictsPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-slate-100 animate-pulse" />}>
      <ConflictManagementWorkspace />
    </Suspense>
  );
}
