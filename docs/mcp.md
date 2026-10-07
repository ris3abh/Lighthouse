# Lighthouse in your AI tools (MCP)

`lighthouse-gc mcp` serves your case to any MCP-capable tool over stdio, on your machine. Nothing leaves your
computer except what that tool's own model sees in the conversation.

What the tools can do:

| Tool | Does |
|---|---|
| `get_scoreboard`, `list_gaps` | read where the case stands |
| `query_claims`, `get_provenance`, `what_changed` | read facts with the exact words they came from |
| `propose_context` | send a note to your **Inbox** (for example "Accepted to judge HackMIT on Nov 8") |

`propose_context` is the only write. A note arrives in the Inbox under "Context from your AI tools", marked
self-reported. You decide whether to keep it. A note is kept as a self-reported note: it never becomes
evidence and never counts toward a criterion. The tool accepts up to 4,000 characters, and sending the same
note twice does nothing.

## Claude Code

```sh
claude mcp add lighthouse --scope user -- lighthouse-gc mcp -w ~/my-case
```

Then, in any session: "What changed in my Lighthouse case this week?" When you mention something worth
keeping, Claude can offer to send it to your Inbox.

## Claude desktop

Open Settings, Developer, Edit Config (`~/Library/Application Support/Claude/claude_desktop_config.json` on
macOS, `%APPDATA%\Claude\claude_desktop_config.json` on Windows). Add:

```json
{
  "mcpServers": {
    "lighthouse": {
      "command": "/full/path/to/lighthouse-gc",
      "args": ["mcp", "-w", "/full/path/to/my-case"]
    }
  }
}
```

Find the full path with `which lighthouse-gc`, because Claude desktop doesn't read your shell's PATH. Restart
Claude desktop; Lighthouse appears in the tools menu. Claude asks before it calls `propose_context`, the same
as for any tool that writes.

## Other MCP clients

Any client that launches stdio servers works with the same command and arguments. To check it by hand:
`npx @modelcontextprotocol/inspector lighthouse-gc mcp -w ~/my-case`.
