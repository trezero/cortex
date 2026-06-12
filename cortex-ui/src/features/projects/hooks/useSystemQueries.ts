import { useQuery } from "@tanstack/react-query";
import { STALE_TIMES } from "@/features/shared/config/queryPatterns";
import { systemService } from "../services/systemService";

export const systemKeys = {
  all: ["systems"] as const,
  lists: () => [...systemKeys.all, "list"] as const,
};

export function useSystems() {
  return useQuery({
    queryKey: systemKeys.lists(),
    queryFn: () => systemService.listSystems(),
    staleTime: STALE_TIMES.rare,
  });
}
