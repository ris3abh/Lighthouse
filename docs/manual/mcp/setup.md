# Set up your agent

Connect Claude Code, Claude Desktop, Codex or any other MCP client to your case in a few minutes.

Every client runs the same command:

```sh
areao1 mcp -w ~/my-case
```

Replace `~/my-case` with your workspace folder (the one with `areao1.yaml` in it). If you leave out `-w`, Area O1 looks for a workspace in this order: the `AREAO1_WORKSPACE` environment variable, the nearest parent of the current folder that has an `areao1.yaml`, then the workspace you opened last. Passing `-w` is the safest choice, because a client may start the server from any folder.

The server talks to the client over stdin and stdout, so you never run it by hand except to test it.

## Claude Code

1. Add the server:

    ```sh
    claude mcp add areao1 -- areao1 mcp -w ~/my-case
    ```

    This adds it for the current project. To have it in every project, add `--scope user`:

    ```sh
    claude mcp add areao1 --scope user -- areao1 mcp -w ~/my-case
    ```

2. Check it: `claude mcp list` should show `areao1`.
3. In a session, ask: "What changed in my Area O1 case this week?"

When you mention something worth keeping, Claude can offer to send it to your Inbox. If you open Claude Code inside the workspace folder, it also picks up the [skill pack](skill-pack.md).

## Claude Desktop

1. Find the full path to `areao1`. Claude Desktop doesn't read your shell's PATH, so it needs the full path.
    - macOS or Linux: `which areao1`
    - Windows: `where areao1`
2. Open Claude Desktop's Settings, then Developer, then Edit Config. This opens `claude_desktop_config.json`:
    - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
    - Windows: `%APPDATA%\Claude\claude_desktop_config.json`
3. Add an `areao1` entry under `mcpServers`, with full paths for both the command and the workspace:

    ```json
    {
      "mcpServers": {
        "areao1": {
          "command": "/full/path/to/areao1",
          "args": ["mcp", "-w", "/full/path/to/my-case"]
        }
      }
    }
    ```

    If the file already has other servers, add `areao1` next to them inside the same `mcpServers` object. On Windows, write backslashes in JSON as `\\` (for example `"C:\\Users\\maya\\my-case"`).

4. Restart Claude Desktop. Area O1 appears in the tools menu.

Claude asks before it calls `propose_context`, the same as for any tool that writes.

## Codex

1. Add the server:

    ```sh
    codex mcp add areao1 -- areao1 mcp -w ~/my-case
    ```

2. Or add it by hand to `~/.codex/config.toml`:

    ```toml
    [mcp_servers.areao1]
    command = "areao1"
    args = ["mcp", "-w", "/full/path/to/my-case"]
    ```

    Use the full path for the workspace here. If Codex can't find `areao1`, put its full path in `command` too.

If you run Codex inside the workspace folder, it reads the workspace's `AGENTS.md`, which explains the tools and rules (see [the skill pack](skill-pack.md)).

## Other MCP clients

Any client that launches stdio servers works. Give it:

- command: `areao1` (or its full path)
- arguments: `mcp`, `-w`, and your workspace's full path

## Check that it works

1. Test the server by hand with the MCP Inspector (needs Node.js):

    ```sh
    npx @modelcontextprotocol/inspector areao1 mcp -w ~/my-case
    ```

    It opens a page where you can list the six tools and call `get_scoreboard`.

2. In your client, ask something only the case can answer, such as "Which criteria are banked in my Area O1 case?" The answer should come from a `get_scoreboard` call.

If it doesn't connect:

| What you see | What to try |
|---|---|
| "No workspace found" | Pass `-w` with the workspace's full path. Check that the folder has `areao1.yaml`. |
| The client can't start `areao1` | Use the full path from `which areao1` or `where areao1`. |
| Old answers after you changed workspaces | Update `-w` in the client's config and restart the client. |

More in [Troubleshooting](../reference/troubleshooting.md).
