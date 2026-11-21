"use client";

import { Suspense } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import { SuccessorOnboardingWorkspace } from "../../../../components/onboarding/SuccessorOnboardingWorkspace";

function ProjectOnboardingInner() {
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const projectId = typeof params?.id === "string" ? params.id : "";
  const caseId = searchParams.get("caseId");
  const versionId = searchParams.get("versionId");

  return (
    <SuccessorOnboardingWorkspace
      projectId={projectId}
      initialCaseId={caseId}
      initialVersionId={versionId}
    />
  );
}

export default function ProjectOnboardingPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-[240px] items-center justify-center">
          <Loader2 className="size-6 animate-spin text-[#315FBA]" />
        </div>
      }
    >
      <ProjectOnboardingInner />
    </Suspense>
  );
}
