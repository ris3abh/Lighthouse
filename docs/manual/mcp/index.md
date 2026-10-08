# MCP and agents

Area O1 has an MCP server, so Claude Code, Claude Desktop, Codex and other AI tools can read your case and leave notes in your Inbox.

## What it is

`areao1 mcp` starts a [Model Context Protocol](https://modelcontextprotocol.io) server over stdio. Your AI tool launches it as a local process; it reads one workspace on your computer. There is no network port and no account.

Nothing leaves your computer except what your AI tool's own model sees in the conversation: the answers the tools return, when the tool calls them.

## Why use it

Area O1's own agent runs inside the app, on OpenAI (see [the Agent page](../tour/agent.md)). The MCP server is for the tools you already work in. With it you can:

- ask "what changed in my case this week?" from your editor or chat app,
- check which criteria are banked and what each one still needs,
- look up a fact and see the exact words it came from,
- save something you mention in passing ("I was asked to judge a hackathon on Nov 8") to your Inbox, to review later.

Your AI tool needs no OpenAI key for any of this.

## What it exposes

| Tool | What it does |
|---|---|
| `get_scoreboard` | Each criterion: banked, building, gap or dropped. |
| `list_gaps` | What each unbanked criterion still needs. |
| `query_claims` | Facts about a repo, paper, person or event, each quoting its source. |
| `get_provenance` | The full trail behind one fact. |
| `what_changed` | Everything recorded since a date. |
| `propose_context` | The only write: a note to your Inbox, marked self-reported. |

Five tools only read. `propose_context` adds a note to your Inbox and nothing else. A note never becomes evidence and never counts toward a criterion.

## In this section

- [Set up your agent](setup.md): connect Claude Code, Claude Desktop, Codex or another MCP client.
- [The skill pack](skill-pack.md): the instructions Area O1 puts in every workspace for Claude Code and Codex.
- [MCP tools](tools.md): every tool, its parameters, what it returns, and example prompts.
- [What agents can and can't do](limits.md): the limits, for MCP clients and for the in-app agent.
