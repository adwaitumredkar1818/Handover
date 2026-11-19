import { api } from "./api";
import { getCachedGraph, setCachedGraph } from "./graphCache";

const inFlightPrefetches = new Map<string, Promise<void>>();
const PREFETCH_CONCURRENCY = 2;

async function runWithConcurrency(
  factories: Array<() => Promise<unknown>>,
  concurrency: number
): Promise<void> {
  let cursor = 0;
  const workers = Array.from(
    { length: Math.min(concurrency, factories.length) },
    async () => {
      while (cursor < factories.length) {
        const idx = cursor++;
        const fn = factories[idx];
        if (!fn) continue;
        try {
          await fn();
        } catch {
          // Background prefetch must never fail loudly
        }
      }
    }
  );
  await Promise.allSettled(workers);
}

/**
 * Background-warm all project graphs, domains, and relationship assets into
 * `graphCache` with bounded concurrency so the active page's requests finish
 * first while subsequent page/subpage switches render in 0ms.
 */
export function prefetchProjectAssets(
  projectId: string,
  userId?: string | null
): Promise<void> {
  if (!projectId) return Promise.resolve();
  const dedupeKey = `${userId ?? "anon"}:${projectId}`;
  const existing = inFlightPrefetches.get(dedupeKey);
  if (existing) return existing;

  const job = (async () => {
    const tasks: Array<() => Promise<unknown>> = [];

    // 1. Knowledge Intelligence: Domains + 3 graph modes
    const kiDomainsKey = `ki_domains:${projectId}:all`;
    if (!getCachedGraph(kiDomainsKey, undefined, userId)) {
      tasks.push(() =>
        api.knowledgeIntelligence
          .listFindings(projectId, undefined, 100, 0)
          .then((res) => {
            setCachedGraph(kiDomainsKey, res.items || [], userId);
          })
          .catch(() => {})
      );
    }

    for (const mode of [
      "technology-stack",
      "system-architecture",
      "features-workflows",
    ] as const) {
      const kiGraphKey = `ki_graph:${projectId}:${mode}:all:all:true:`;
      if (!getCachedGraph(kiGraphKey, undefined, userId)) {
        tasks.push(() =>
          api.knowledgeIntelligence
            .getGraph(projectId, mode, { include_suggested: true })
            .then((res) => {
              setCachedGraph(
                kiGraphKey,
                { nodes: res.nodes || [], edges: res.edges || [] },
                userId
              );
            })
            .catch(() => {})
        );
      }
    }

    // 2. Relationship Explorer: Contributors graph + entities graph + selectable members + all subpages
    const relContribsKey = `rel_contribs:${projectId}:_:_:_:true:true:_:_`;
    const relContribListKey = `rel_contrib_list:${projectId}`;
    const relClustersKey = `rel_clusters:${projectId}`;
    const needRelContribs = !getCachedGraph(relContribsKey, undefined, userId);
    const needRelContribList = !getCachedGraph(relContribListKey, undefined, userId);
    const needRelClusters = !getCachedGraph(relClustersKey, undefined, userId);

    if (needRelContribs) {
      tasks.push(() =>
        Promise.all([
          api.relationships.getContributorsGraph(projectId, {
            include_external: true,
            include_bots: true,
          }),
          api.relationships.listContributors(projectId),
          api.relationships.listWorkClusters(projectId),
        ])
          .then(([graphRes, contribList, clusterList]) => {
            setCachedGraph(
              relContribsKey,
              { graphRes, contribList, clusterList },
              userId
            );
            setCachedGraph(relContribListKey, contribList, userId);
            setCachedGraph(relClustersKey, clusterList, userId);
          })
          .catch(() => {})
      );
    } else {
      if (needRelContribList) {
        tasks.push(() =>
          api.relationships
            .listContributors(projectId)
            .then((contribList) => {
              setCachedGraph(relContribListKey, contribList, userId);
            })
            .catch(() => {})
        );
      }
      if (needRelClusters) {
        tasks.push(() =>
          api.relationships
            .listWorkClusters(projectId)
            .then((clusterList) => {
              setCachedGraph(relClustersKey, clusterList, userId);
            })
            .catch(() => {})
        );
      }
    }

    const relEntitiesKey = `rel_entities:${projectId}`;
    if (!getCachedGraph(relEntitiesKey, undefined, userId)) {
      tasks.push(() =>
        api.relationships
          .getGraph(projectId)
          .then((graphData) => {
            setCachedGraph(relEntitiesKey, graphData, userId);
          })
          .catch(() => {})
      );
    }

    const relSelectableKey = `rel_selectable:${projectId}`;
    if (!getCachedGraph(relSelectableKey, undefined, userId)) {
      tasks.push(() =>
        api.relationships
          .listSelectableMembers(projectId)
          .then((res) => {
            if (Array.isArray(res)) {
              setCachedGraph(relSelectableKey, res, userId);
            }
          })
          .catch(() => {})
      );
    }

    const relCandidatesKey = `rel_candidates:${projectId}`;
    if (!getCachedGraph(relCandidatesKey, undefined, userId)) {
      tasks.push(() =>
        api.relationships
          .listIdentityCandidates(projectId)
          .then((candList) => {
            setCachedGraph(relCandidatesKey, candList, userId);
          })
          .catch(() => {})
      );
    }

    const relAttributionsKey = `rel_attributions:${projectId}`;
    if (!getCachedGraph(relAttributionsKey, undefined, userId)) {
      tasks.push(() =>
        api.roster
          .listAttributions(projectId)
          .then((attrs) => {
            setCachedGraph(relAttributionsKey, attrs, userId);
          })
          .catch(() => {})
      );
    }

    const relTraceabilityKey = `rel_traceability:${projectId}`;
    if (!getCachedGraph(relTraceabilityKey, undefined, userId)) {
      tasks.push(() =>
        api.relationships
          .getTraceability(projectId)
          .then((res) => {
            const rawList =
              (res as { chains?: unknown[]; items?: unknown[] }).chains ||
              (res as { items?: unknown[] }).items ||
              [];
            const mapped = rawList.map((tc: unknown) => {
              const row = tc as Record<string, unknown>;
              return {
                ...row,
                decision_name: (row.decision_name as string) || "Untitled Decision",
                work_item_count:
                  (row.work_item_count as number | undefined) ??
                  ((row.work_item_ids as unknown[] | undefined)?.length ?? 0),
                pr_count:
                  (row.pr_count as number | undefined) ??
                  ((row.pull_request_ids as unknown[] | undefined)?.length ?? 0),
                commit_count:
                  (row.commit_count as number | undefined) ??
                  ((row.commit_ids as unknown[] | undefined)?.length ?? 0),
                component_count:
                  (row.component_count as number | undefined) ??
                  ((row.component_ids as unknown[] | undefined)?.length ?? 0),
                missing_links: (row.missing_links as string[] | undefined) || [],
              };
            });
            setCachedGraph(relTraceabilityKey, mapped, userId);
          })
          .catch(() => {})
      );
    }

    const relDependenciesKey = `rel_dependencies:${projectId}`;
    if (!getCachedGraph(relDependenciesKey, undefined, userId)) {
      tasks.push(() =>
        api.relationships
          .getDependencies(projectId)
          .then((res) => {
            const r = res as {
              nodes?: unknown[];
              edges?: unknown[];
              cycles?: unknown[];
              detected_cycles?: unknown[];
              root_blockers?: unknown[];
            };
            setCachedGraph(
              relDependenciesKey,
              {
                nodes: r.nodes || [],
                edges: r.edges || [],
                cycles: r.cycles || r.detected_cycles || [],
                root_blockers: r.root_blockers || [],
              },
              userId
            );
          })
          .catch(() => {})
      );
    }

    const relTimelineKey = `rel_timeline:${projectId}`;
    if (!getCachedGraph(relTimelineKey, undefined, userId)) {
      tasks.push(() =>
        api.relationships
          .getTimeline(projectId)
          .then((res) => {
            setCachedGraph(
              relTimelineKey,
              (res as { items?: unknown[] }).items || [],
              userId
            );
          })
          .catch(() => {})
      );
    }

    if (tasks.length > 0) {
      await runWithConcurrency(tasks, PREFETCH_CONCURRENCY);
    }
  })().finally(() => {
    inFlightPrefetches.delete(dedupeKey);
  });

  inFlightPrefetches.set(dedupeKey, job);
  return job;
}

const inFlightOrgPrefetches = new Map<string, Promise<void>>();

/**
 * Background-warm organisation-level assets (team members, invitations,
 * connected sources) so Admin / Team / Sources pages open immediately.
 */
export function prefetchOrganisationAssets(
  orgId: string,
  userId?: string | null
): Promise<void> {
  if (!orgId) return Promise.resolve();
  const dedupeKey = `${userId ?? "anon"}:org:${orgId}`;
  const existing = inFlightOrgPrefetches.get(dedupeKey);
  if (existing) return existing;

  const job = runWithConcurrency(
    [
      () => {
        const key = `org_members:${orgId}`;
        if (getCachedGraph(key, undefined, userId)) return Promise.resolve();
        return api.organisations
          .listMembers(orgId)
          .then((res) => setCachedGraph(key, res, userId))
          .catch(() => {});
      },
      () => {
        const key = `org_invitations:${orgId}:pending`;
        if (getCachedGraph(key, undefined, userId)) return Promise.resolve();
        return api.organisations
          .listInvitations(orgId, { status: "pending" })
          .then((res) => setCachedGraph(key, res, userId))
          .catch(() => {});
      },
      () => {
        const key = `org_sources:${orgId}`;
        if (getCachedGraph(key, undefined, userId)) return Promise.resolve();
        return api.sources
          .listOrgConnections(orgId)
          .then((res) => setCachedGraph(key, res, userId))
          .catch(() => {});
      },
    ],
    PREFETCH_CONCURRENCY
  ).finally(() => {
    inFlightOrgPrefetches.delete(dedupeKey);
  });

  inFlightOrgPrefetches.set(dedupeKey, job);
  return job;
}

/**
 * Background-warm every project in the workspace sequentially (active project
 * first, then remaining projects) so switching projects or opening any page is instant.
 */
export async function prefetchAllWorkspaceProjects(
  projectIds: string[],
  activeProjectId?: string | null,
  userId?: string | null
): Promise<void> {
  const ordered = [
    ...(activeProjectId ? [activeProjectId] : []),
    ...projectIds.filter((id) => id && id !== activeProjectId),
  ];
  const uniqueIds = Array.from(new Set(ordered));

  for (const pid of uniqueIds) {
    // Warm core project endpoints (overview, members, evidence, verification, handovers)
    await runWithConcurrency(
      [
        () => {
          const key = `proj_overview:${pid}`;
          if (getCachedGraph(key, undefined, userId)) return Promise.resolve();
          return api.projects
            .getOverview(pid)
            .then((res) => setCachedGraph(key, res, userId))
            .catch(() => {});
        },
        () => {
          const key = `proj_members:${pid}`;
          if (getCachedGraph(key, undefined, userId)) return Promise.resolve();
          return api.members
            .list(pid)
            .then((res) => setCachedGraph(key, res, userId))
            .catch(() => {});
        },
        () => {
          const key = `proj_evidence:${pid}`;
          if (getCachedGraph(key, undefined, userId)) return Promise.resolve();
          return api.evidence
            .list(pid)
            .then((res) => setCachedGraph(key, res, userId))
            .catch(() => {});
        },
        () => {
          const key = `proj_verification:${pid}`;
          if (getCachedGraph(key, undefined, userId)) return Promise.resolve();
          return api.verification
            .getQueue(pid)
            .then((res) => setCachedGraph(key, res, userId))
            .catch(() => {});
        },
        () => {
          const key = `proj_handovers:${pid}`;
          if (getCachedGraph(key, undefined, userId)) return Promise.resolve();
          return api.handover
            .listCases(pid)
            .then((res) => setCachedGraph(key, res, userId))
            .catch(() => {});
        },
      ],
      PREFETCH_CONCURRENCY
    );
    await prefetchProjectAssets(pid, userId);
  }
}
