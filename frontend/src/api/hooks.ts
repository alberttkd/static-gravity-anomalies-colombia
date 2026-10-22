import { useMutation, useQuery } from "@tanstack/react-query";
import { createContext, useContext } from "react";
import { DEFAULT_REDUCTION } from "../state/store";
import { createSource, type DataSource } from "./source";
import type { GriddingConfig, ReductionConfig } from "./types";

export const SourceContext = createContext<DataSource>(createSource());
export const useSource = () => useContext(SourceContext);

export function useDatasets() {
  const src = useSource();
  return useQuery({ queryKey: ["datasets", src.mode], queryFn: () => src.datasets() });
}

/** Reduction runs are cached by dataset + config (the API caches by config hash too). */
export function useRun(dataset: string, config: Partial<ReductionConfig>) {
  const src = useSource();
  return useQuery({ queryKey: ["run", src.mode, dataset, config], queryFn: () => src.reduce(dataset, config), staleTime: Infinity });
}

export function useReferenceRun(dataset: string) {
  return useRun(dataset, DEFAULT_REDUCTION);
}

export function useStations(runId: string | null | undefined) {
  const src = useSource();
  return useQuery({
    queryKey: ["stations", src.mode, runId],
    queryFn: () => src.stations(runId as string),
    enabled: !!runId,
    staleTime: Infinity,
  });
}

export function useQc(dataset: string) {
  const src = useSource();
  return useQuery({ queryKey: ["qc", src.mode, dataset], queryFn: () => src.qc(dataset), staleTime: Infinity });
}

export function useDensity(dataset: string, densities: [number, number], enabled: boolean) {
  const src = useSource();
  return useQuery({
    queryKey: ["density", src.mode, dataset, densities],
    queryFn: () => src.density(dataset, densities),
    enabled,
    staleTime: Infinity,
    retry: false,
  });
}

export function useSubmitGrid() {
  const src = useSource();
  return useMutation({ mutationFn: (a: { runId: string; config: Partial<GriddingConfig> }) => src.submitGrid(a.runId, a.config) });
}

export function useJob(jobId: string | null) {
  const src = useSource();
  return useQuery({
    queryKey: ["job", src.mode, jobId],
    queryFn: () => src.job(jobId as string),
    enabled: !!jobId,
    refetchInterval: (q) => (q.state.data && (q.state.data.status === "done" || q.state.data.status === "failed") ? false : 800),
  });
}

export function useGrid(gridId: string | null) {
  const src = useSource();
  return useQuery({ queryKey: ["grid", src.mode, gridId], queryFn: () => src.grid(gridId as string), enabled: !!gridId, staleTime: Infinity });
}

export function useLayerImage(gridId: string | null, layer: string, enabled = true) {
  const src = useSource();
  return useQuery({
    queryKey: ["img", src.mode, gridId, layer],
    queryFn: () => src.layerImage(gridId as string, layer),
    enabled: !!gridId && enabled,
    staleTime: Infinity,
    retry: false,
  });
}

export function useContours(gridId: string | null, layer: string, enabled: boolean) {
  const src = useSource();
  return useQuery({
    queryKey: ["contours", src.mode, gridId, layer],
    queryFn: () => src.contours(gridId as string, layer),
    enabled: !!gridId && enabled,
    staleTime: Infinity,
  });
}

export function useValidation(gridId: string | null) {
  const src = useSource();
  return useQuery({ queryKey: ["validation", src.mode, gridId], queryFn: () => src.validation(gridId as string), enabled: !!gridId, staleTime: Infinity });
}

export function useProfile() {
  const src = useSource();
  return useMutation({
    mutationFn: (a: { gridId: string; coordinates: [number, number][]; bufferM: number }) => src.profile(a.gridId, a.coordinates, a.bufferM),
  });
}

export function useManifest(runId: string | null | undefined) {
  const src = useSource();
  return useQuery({ queryKey: ["manifest", src.mode, runId], queryFn: () => src.manifest(runId as string), enabled: !!runId, staleTime: Infinity });
}
