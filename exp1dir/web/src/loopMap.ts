export const NODES = ["task", "reason", "act", "observe", "success", "learn", "memory_update", "reuse"] as const;
export const STEPS: Record<string, string> = {
  reason: "reason",
  act: "act",
  observe: "observe",
  success: "success",
  learn: "learn",
  memory_update: "memory_update",
  error: "observe",
};
export function nodeForStep(step: string): string {
  return STEPS[step] ?? step;
}
