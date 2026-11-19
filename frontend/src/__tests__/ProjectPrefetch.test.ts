import { beforeEach, describe, expect, it, vi } from "vitest";
import { getCachedGraph, invalidateGraphCache, setGraphCacheUser } from "../lib/graphCache";

const mockListFindings = vi.fn(async (..._args: unknown[]) => ({ items: [{ id: "f1" }] }));
const mockGetKiGraph = vi.fn(async (..._args: unknown[]) => ({ nodes: [{ id: "n1" }], edges: [] }));
const mockGetContributorsGraph = vi.fn(async (..._args: unknown[]) => ({ nodes: [{ id: "p1" }], edges: [] }));
const mockListContributors = vi.fn(async (..._args: unknown[]) => [{ contributor_key: "c1" }]);
const mockListWorkClusters = vi.fn(async (..._args: unknown[]) => [{ cluster_id: "wc1" }]);
const mockGetRelGraph = vi.fn(async (..._args: unknown[]) => ({ nodes: [{ id: "e1" }], edges: [] }));
const mockListSelectableMembers = vi.fn(async (..._args: unknown[]) => [{ selection_key: "pm:1" }]);
const mockListIdentityCandidates = vi.fn(async (..._args: unknown[]) => [{ id: "cand1" }]);
const mockListAttributions = vi.fn(async (..._args: unknown[]) => [{ id: "attr1" }]);
const mockGetTraceability = vi.fn(async (..._args: unknown[]) => ({ chains: [{ id: "tc1", decision_name: "Auth" }] }));
const mockGetDependencies = vi.fn(async (..._args: unknown[]) => ({ nodes: [{ id: "d1" }], edges: [], cycles: [], root_blockers: [] }));
const mockGetTimeline = vi.fn(async (..._args: unknown[]) => ({ items: [{ id: "ev1" }] }));

vi.mock("../lib/api", () => ({
  api: {
    knowledgeIntelligence: {
      listFindings: (...args: unknown[]) => mockListFindings(...args),
      getGraph: (...args: unknown[]) => mockGetKiGraph(...args),
    },
    relationships: {
      getContributorsGraph: (...args: unknown[]) => mockGetContributorsGraph(...args),
      listContributors: (...args: unknown[]) => mockListContributors(...args),
      listWorkClusters: (...args: unknown[]) => mockListWorkClusters(...args),
      getGraph: (...args: unknown[]) => mockGetRelGraph(...args),
      listSelectableMembers: (...args: unknown[]) => mockListSelectableMembers(...args),
      listIdentityCandidates: (...args: unknown[]) => mockListIdentityCandidates(...args),
      getTraceability: (...args: unknown[]) => mockGetTraceability(...args),
      getDependencies: (...args: unknown[]) => mockGetDependencies(...args),
      getTimeline: (...args: unknown[]) => mockGetTimeline(...args),
    },
    roster: {
      listAttributions: (...args: unknown[]) => mockListAttributions(...args),
    },
  },
}));

import { prefetchProjectAssets } from "../lib/projectPrefetch";

describe("prefetchProjectAssets", () => {
  beforeEach(() => {
    invalidateGraphCache();
    setGraphCacheUser("user-1");
    vi.clearAllMocks();
  });

  it("warms all Knowledge Intelligence and Relationship Explorer graph caches and skips subsequent redundant calls", async () => {
    await prefetchProjectAssets("proj-123", "user-1");

    expect(mockListFindings).toHaveBeenCalledTimes(1);
    expect(mockGetKiGraph).toHaveBeenCalledTimes(3);
    expect(mockGetContributorsGraph).toHaveBeenCalledTimes(1);
    expect(mockListContributors).toHaveBeenCalledTimes(1);
    expect(mockListWorkClusters).toHaveBeenCalledTimes(1);
    expect(mockGetRelGraph).toHaveBeenCalledTimes(1);
    expect(mockListSelectableMembers).toHaveBeenCalledTimes(1);
    expect(mockListIdentityCandidates).toHaveBeenCalledTimes(1);

    expect(getCachedGraph("ki_domains:proj-123:all", undefined, "user-1")).toEqual([{ id: "f1" }]);
    expect(getCachedGraph("ki_graph:proj-123:technology-stack:all:all:true:", undefined, "user-1")).toEqual({
      nodes: [{ id: "n1" }],
      edges: [],
    });
    expect(getCachedGraph("ki_graph:proj-123:system-architecture:all:all:true:", undefined, "user-1")).toEqual({
      nodes: [{ id: "n1" }],
      edges: [],
    });
    expect(getCachedGraph("ki_graph:proj-123:features-workflows:all:all:true:", undefined, "user-1")).toEqual({
      nodes: [{ id: "n1" }],
      edges: [],
    });
    expect(getCachedGraph("rel_contribs:proj-123:_:_:_:true:true:_:_", undefined, "user-1")).toBeTruthy();
    expect(getCachedGraph("rel_entities:proj-123", undefined, "user-1")).toBeTruthy();
    expect(getCachedGraph("rel_selectable:proj-123", undefined, "user-1")).toEqual([{ selection_key: "pm:1" }]);
    expect(getCachedGraph("rel_contrib_list:proj-123", undefined, "user-1")).toEqual([{ contributor_key: "c1" }]);
    expect(getCachedGraph("rel_candidates:proj-123", undefined, "user-1")).toEqual([{ id: "cand1" }]);
    expect(getCachedGraph("rel_clusters:proj-123", undefined, "user-1")).toEqual([{ cluster_id: "wc1" }]);
    expect(getCachedGraph("rel_attributions:proj-123", undefined, "user-1")).toEqual([{ id: "attr1" }]);
    expect(getCachedGraph("rel_traceability:proj-123", undefined, "user-1")).toBeTruthy();
    expect(getCachedGraph("rel_dependencies:proj-123", undefined, "user-1")).toBeTruthy();
    expect(getCachedGraph("rel_timeline:proj-123", undefined, "user-1")).toEqual([{ id: "ev1" }]);

    // Second call skips all network requests since everything is cached
    await prefetchProjectAssets("proj-123", "user-1");
    expect(mockListFindings).toHaveBeenCalledTimes(1);
    expect(mockGetKiGraph).toHaveBeenCalledTimes(3);
    expect(mockGetRelGraph).toHaveBeenCalledTimes(1);
  });
});
