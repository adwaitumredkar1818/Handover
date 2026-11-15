"use client";

import React, { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import { AuthPage } from "../../components/figma-pages/AuthPage";
import { SuccessorOnboardingWorkspace } from "../../components/onboarding/SuccessorOnboardingWorkspace";

function OnboardingRouter() {
  const searchParams = useSearchParams();
  const projectId = searchParams.get("project");

  if (projectId) {
    return <SuccessorOnboardingWorkspace projectId={projectId} />;
  }

  return <AuthPage view="onboarding" />;
}

export default function OnboardingRoute() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center">
          <Loader2 className="size-6 animate-spin text-[#315FBA]" />
        </div>
      }
    >
      <OnboardingRouter />
    </Suspense>
  );
}
