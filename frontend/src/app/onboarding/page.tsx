"use client";

import React, { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import { AuthPage } from "../../components/figma-pages/AuthPage";
import { SuccessorOnboardingWorkspace } from "../../components/onboarding/SuccessorOnboardingWorkspace";
import { useLiveApp } from "../../context/LiveAppContext";

function OnboardingRouter() {
  const searchParams = useSearchParams();
  const { activeProject, projects, user } = useLiveApp();
  const queryProjectId = searchParams.get("project");
  const queryCaseId = searchParams.get("caseId");
  const queryVersionId = searchParams.get("versionId");
  const effectiveProjectId =
    queryProjectId || activeProject?.id || (user && projects.length > 0 ? projects[0]?.id : null);

  if (effectiveProjectId) {
    return (
      <SuccessorOnboardingWorkspace
        projectId={effectiveProjectId}
        initialCaseId={queryCaseId}
        initialVersionId={queryVersionId}
      />
    );
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
