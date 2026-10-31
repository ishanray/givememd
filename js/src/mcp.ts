#!/usr/bin/env node
/** MCP server (stdio): every fetch runs on the caller's machine, from the caller's own connection.
 *   claude mcp add givememd -- npx -y givememd-mcp */
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { z } from 'zod';
import { read, UnsafeURL } from './index.js';

const server = new McpServer({ name: 'givememd', version: '0.1.0' });
server.registerTool('read_url', {
  description: 'Read any web page as clean, LLM-ready markdown: page text, structured data hidden in the page (listings, products) as tables, and cleaned links. Fetches from this machine.',
  inputSchema: { url: z.string().describe('URL or bare domain, e.g. "en.wikipedia.org/wiki/Markdown"'), links: z.boolean().optional() },
}, async ({ url, links }) => {
  try {
    const { markdown, result } = await read(url, { links: links ?? true });
    const textOut = markdown ?? `Could not read ${result.url}. Tiers tried:\n${result.trace.join('\n')}`;
    return { content: [{ type: 'text', text: textOut }] };
  } catch (e) {
    return { content: [{ type: 'text', text: e instanceof UnsafeURL ? `Refused: ${e.message}` : `Error: ${(e as Error).message}` }], isError: true };
  }
});
await server.connect(new StdioServerTransport());
