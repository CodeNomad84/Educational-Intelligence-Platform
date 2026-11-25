/**
 * Platform Admin (Ministry) client — `GET /api/platform/global-stats/` (django_core/dashboard/platform_api.py).
 * Aggregate counters only: total schools, active users by role and active-module counts. No names.
 */
import { apiFetch } from "./api";

export interface RoleCount {
  role: string;
  label: string;
  count: number;
}

export interface ModuleStat {
  key: string;
  label: string;
  active_schools: number;
}

export interface GlobalStats {
  generated_at: string;
  schools_total: number;
  users_total: number;
  users_by_role: RoleCount[];
  modules: ModuleStat[];
}

export function fetchGlobalStats(): Promise<GlobalStats> {
  return apiFetch<GlobalStats>("/platform/global-stats/");
}
