"use client";

import { useParams } from "next/navigation";
import { SuccessorOnboardingWorkspace } from "../../../../components/onboarding/SuccessorOnboardingWorkspace";

export default function ProjectOnboardingPage() {
  const params = useParams<{ id: string }>();
  const projectId = typeof params?.id === "string" ? params.id : "";

  return <SuccessorOnboardingWorkspace projectId={projectId} />;
}
