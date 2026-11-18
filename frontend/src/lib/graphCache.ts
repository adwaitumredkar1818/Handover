/**
 * High-performance client-side graph cache.
 * 
 * Provides two-tier caching (in-memory Map + sessionStorage) so that
 * once a graph is loaded, subsequent tab switches, mode toggles, and
 * page navigations render in 0ms without repeated network requests or spinners.
 */

interface CacheEntry<T> {
  data: T;
  timestamp: number;
  userId?: string | null;
}

const memoryCache = new Map<string, CacheEntry<unknown>>();
const DEFAULT_TTL_MS = 10 * 60 * 1000; // 10 minutes
let currentActiveUserId: string | null = null;

export function setGraphCacheUser(userId: string | null): void {
  if (currentActiveUserId !== userId) {
    // Purge previous user's graph cache to guarantee cross-user isolation
    invalidateGraphCache();
    currentActiveUserId = userId;
  }
}

export function getGraphCacheUser(): string | null {
  return currentActiveUserId;
}

function getStorageKey(key: string, userId?: string | null): string {
  const uid = userId !== undefined ? userId : currentActiveUserId;
  return `handover_gc_${uid ? `u_${uid}_` : ""}${key}`;
}

export function getCachedGraph<T>(key: string, maxAgeMs = DEFAULT_TTL_MS, userId?: string | null): T | null {
  if (!key || key.includes("::")) return null;
  const now = Date.now();
  const effectiveUser = userId !== undefined ? userId : currentActiveUserId;

  // Tier 1: Fast in-memory lookup (0ms)
  const mem = memoryCache.get(key);
  if (mem && now - mem.timestamp < maxAgeMs) {
    if (mem.userId !== undefined && mem.userId !== effectiveUser) {
      memoryCache.delete(key);
      return null;
    }
    return mem.data as T;
  }

  // Tier 2: sessionStorage (persists across workspace page navigation)
  if (typeof window !== "undefined") {
    try {
      const storageKey = getStorageKey(key, effectiveUser);
      const raw = sessionStorage.getItem(storageKey);
      if (raw) {
        const parsed: CacheEntry<T> = JSON.parse(raw);
        if (now - parsed.timestamp < maxAgeMs) {
          if (parsed.userId !== undefined && parsed.userId !== effectiveUser) {
            sessionStorage.removeItem(storageKey);
            return null;
          }
          memoryCache.set(key, parsed);
          return parsed.data;
        } else {
          sessionStorage.removeItem(storageKey);
        }
      }
    } catch {
      // Ignore sessionStorage parsing or quota errors
    }
  }

  return null;
}

export function setCachedGraph<T>(key: string, data: T, userId?: string | null): void {
  if (!key || key.includes("::")) return;
  const effectiveUser = userId !== undefined ? userId : currentActiveUserId;
  const entry: CacheEntry<T> = {
    data,
    timestamp: Date.now(),
    userId: effectiveUser,
  };

  memoryCache.set(key, entry);

  if (typeof window !== "undefined") {
    const storageKey = getStorageKey(key, effectiveUser);
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(entry));
    } catch {
      // If sessionStorage quota exceeded, safely clear older graph cache entries
      try {
        clearOldSessionStorage();
        sessionStorage.setItem(storageKey, JSON.stringify(entry));
      } catch {
        // Fall back to memory cache only
      }
    }
  }
}

export function invalidateGraphCache(prefix?: string): void {
  // Clear from in-memory cache
  if (!prefix) {
    memoryCache.clear();
  } else {
    for (const k of Array.from(memoryCache.keys())) {
      if (k.startsWith(prefix) || k.includes(prefix)) {
        memoryCache.delete(k);
      }
    }
  }

  // Clear from sessionStorage
  if (typeof window !== "undefined") {
    try {
      const storagePrefix = prefix ? getStorageKey(prefix) : "handover_gc_";
      const keysToRemove: string[] = [];
      for (let i = 0; i < sessionStorage.length; i++) {
        const k = sessionStorage.key(i);
        if (k && (prefix ? k.includes(prefix) : k.startsWith(storagePrefix))) {
          keysToRemove.push(k);
        }
      }
      keysToRemove.forEach((k) => sessionStorage.removeItem(k));
    } catch {
      // Ignore
    }
  }
}

function clearOldSessionStorage(): void {
  if (typeof window === "undefined") return;
  const keys: string[] = [];
  for (let i = 0; i < sessionStorage.length; i++) {
    const k = sessionStorage.key(i);
    if (k && k.startsWith("handover_gc_")) {
      keys.push(k);
    }
  }
  keys.forEach((k) => sessionStorage.removeItem(k));
}
