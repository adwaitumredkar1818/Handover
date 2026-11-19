import { useState, useCallback, useMemo } from "react";

export interface ProgressStage {
  id: string;
  label: string;
  description?: string;
}

export interface UseProgressStateOptions {
  stages: ProgressStage[];
  initialStageId?: string;
}

export function useProgressState(options: UseProgressStateOptions) {
  const { stages, initialStageId } = options;
  const [currentStageIndex, setCurrentStageIndex] = useState<number>(() => {
    if (!initialStageId) return 0;
    const idx = stages.findIndex((s) => s.id === initialStageId);
    return idx >= 0 ? idx : 0;
  });

  const [percent, setPercent] = useState<number | null>(null); // null = indeterminate
  const [stageDetails, setStageDetails] = useState<string | null>(null);

  const currentStage = useMemo(
    () => stages[currentStageIndex] || stages[0],
    [stages, currentStageIndex]
  );

  const isCompleted = currentStageIndex >= stages.length - 1 && percent === 100;

  const nextStage = useCallback(() => {
    setCurrentStageIndex((prev) => Math.min(stages.length - 1, prev + 1));
    setPercent(null);
    setStageDetails(null);
  }, [stages.length]);

  const setStage = useCallback(
    (stageId: string, customDetails?: string) => {
      const idx = stages.findIndex((s) => s.id === stageId);
      if (idx >= 0) {
        setCurrentStageIndex(idx);
        if (customDetails !== undefined) {
          setStageDetails(customDetails);
        }
      }
    },
    [stages]
  );

  const reset = useCallback(() => {
    setCurrentStageIndex(0);
    setPercent(null);
    setStageDetails(null);
  }, []);

  return {
    currentStage,
    currentStageIndex,
    totalStages: stages.length,
    percent,
    stageDetails,
    isCompleted,
    setPercent,
    setStageDetails,
    setStage,
    nextStage,
    reset,
  };
}
