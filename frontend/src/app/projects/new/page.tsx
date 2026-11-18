"use client";

import { useRouter } from "next/navigation";
import { ProjectCreationWizard } from "../../../components/project-workspace/ProjectCreationWizard";

export default function NewProjectRoute() {
  const router = useRouter();
  return (
    <div className="mx-auto max-w-4xl py-6 px-4 sm:px-6">
      <div className="rounded-2xl border border-line bg-white p-6 sm:p-8 shadow-card">
        <ProjectCreationWizard
          onSuccess={(newProj) => {
            if (newProj?.id) {
              router.push(`/projects/${newProj.id}/evidence`);
            }
          }}
          onCancel={() => router.push("/projects")}
        />
      </div>
    </div>
  );
}
