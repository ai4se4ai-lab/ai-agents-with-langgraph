export type McpEvent = {
  tool?: string;
  mcp_server?: string;
  mcp_tool?: string;
};

export type McpServer = {
  name: string;
  transport?: string;
  enabled?: boolean;
  connected?: boolean;
  tools?: string[];
  last_error?: string;
};

export function actLabel(event: McpEvent): string {
  if (event.mcp_server && event.mcp_tool) {
    return `${event.mcp_server} / ${event.mcp_tool}`;
  }
  return event.tool ?? "";
}

export function usedMcps(events: McpEvent[]): string[] {
  const names = events.map((e) => e.mcp_server).filter((n): n is string => Boolean(n));
  return [...new Set(names)];
}
