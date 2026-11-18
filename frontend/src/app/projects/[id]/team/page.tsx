"use client";

import { useParams } from "next/navigation";
import { useLiveApp } from "../../../../context/LiveAppContext";
import { ProjectTeamTab } from "../../../../components/project-workspace/ProjectTeamTab";
import { ProjectsPage } from "../../../../components/figma-pages/ProjectsPage";

export default function ProjectTeamRoute() {
  const params = useParams();
  const id = Array.isArray(params?.id) ? params.id[0] : (params?.id as string | undefined);
  const { projects, activeProject, user } = useLiveApp();

  const isUuid = Boolean(id && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id));
  const matched = (id ? projects.find((p) => p.id === id) : null) || (activeProject?.id === id ? activeProject : null);

  if (isUuid && matched) {
    const canManage =
      matched.my_project_role === "project_manager" ||
      (user?.id != null && matched.owner_id === user.id);
    return (
      <div className="p-6 max-w-6xl mx-auto">
        <ProjectTeamTab project={matched} canManage={canManage} />
      </div>
    );
  }

  return <ProjectsPage view="team" />;
}
