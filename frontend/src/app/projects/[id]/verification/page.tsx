import React, { Suspense } from "react";
import { VerificationCenterWorkspace } from "../../../../components/verification/VerificationCenterWorkspace";

export const instant = false;

export default function ProjectVerificationRoute() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-[#F6F8FC] animate-pulse" />}>
      <VerificationCenterWorkspace />
    </Suspense>
  );
}
