# NightMend MCP Integration

NightMend is the **first open-source monitoring platform with native MCP support + AI analysis**.

## Overview

The Model Context Protocol (MCP) integration exposes NightMend' core operational tools to AI agents, enabling intelligent monitoring and incident response through natural language.

## Competitive Advantage

- **Grafana**: Has official MCP support but lacks AI analysis
- **Zabbix**: Only community MCP implementations  
- **Prometheus**: No native MCP support
- **NightMend**: Native MCP + AI analysis = unique differentiator

## Available Tools

### 1. `get_servers_health`
Get server health status and key metrics.

**Parameters:**
- `limit` (int): Maximum servers to return (default: 10)
- `status_filter` (str): Filter by status (online/offline/warning)

**Example usage:**
"Show me the health of all servers" or "Get servers that are offline"

### 2. `get_alerts` 
Get active alerts with filtering options.

**Parameters:**
- `severity` (str): Filter by severity (critical/warning/info)
- `status` (str): Filter by status (firing/resolved/acknowledged)
- `limit` (int): Maximum alerts (default: 20)
- `hours_back` (int): Look back hours (default: 24)

**Example usage:**
"Show critical alerts from the last 6 hours" or "List all firing alerts"

### 3. `search_logs`
Search logs with keyword and filters.

**Parameters:**
- `keyword` (str): Search keyword in log messages
- `host_id` (int): Filter by specific host ID
- `service` (str): Filter by service name  
- `level` (str): Filter by log level (DEBUG/INFO/WARN/ERROR/FATAL)
- `hours_back` (int): Search in last N hours (default: 1)
- `limit` (int): Maximum log entries (default: 50)

**Example usage:**
"Search for error logs containing 'connection' in the last 2 hours"

### 4. `analyze_incident` 🚀
AI-powered incident root cause analysis (NightMend differentiator).

**Parameters:**
- `alert_id` (int): Specific alert to analyze
- `description` (str): Free-text incident description
- `include_context` (bool): Include related metrics and logs

**Example usage:**
"Analyze the incident for alert ID 123" or "What could cause high CPU usage?"

### 5. `get_topology`
Get service topology and dependency mapping.

**Parameters:**
- `service_id` (int): Focus on specific service (optional)
- `include_dependencies` (bool): Include dependency relationships

**Example usage:**
"Show the service topology" or "Get dependencies for service 5"

## Setup

### Option 1: Standalone MCP Server

1. **Start the MCP server:**
   ```bash
   cd backend
   python -m app.mcp.cli --host 127.0.0.1 --port 8003
   ```

2. **Configure your MCP client** (e.g., Claude Desktop):
   ```json
   {
     "mcpServers": {
       "nightmend": {
         "command": "python",
         "args": ["-m", "app.mcp.cli"],
         "cwd": "./backend"
       }
     }
   }
   ```

### Option 2: Integrated with Main App

Set environment variables and restart the main application:

```bash
export NIGHTMEND_MCP_ENABLED=true
export NIGHTMEND_MCP_HOST=127.0.0.1
export NIGHTMEND_MCP_PORT=8003
```

Then start NightMend normally. The MCP server will run alongside the main API.

## Claude Desktop Integration

1. **Install Claude Desktop** from Anthropic

2. **Add NightMend MCP server** to your configuration:
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Windows: `%APPDATA%\Claude\claude_desktop_config.json`

3. **Configuration example:**
   ```json
   {
     "mcpServers": {
       "nightmend": {
         "command": "python",
         "args": ["-m", "app.mcp.cli"],
         "cwd": "/path/to/nightmend/backend",
         "env": {
           "DATABASE_URL": "postgresql://nightmend:nightmend123@localhost:5433/nightmend"
         }
       }
     }
   }
   ```

4. **Restart Claude Desktop** and you'll see NightMend tools available

## Example Conversations

**Monitor server health:**
> "Check the health of all my servers and tell me which ones need attention"

**Investigate alerts:**  
> "What are the critical alerts in the last hour? Analyze the most severe one."

**Troubleshoot issues:**
> "Search for error logs containing 'database' and help me understand what's happening"

**Incident response:**
> "Analyze alert 456 with full context and give me remediation steps"

## OpenCode Integration

[OpenCode](https://github.com/opencode-ai/opencode) is an open-source AI terminal coding assistant with native MCP support. It can directly connect to NightMend MCP Server for intelligent ops interaction.

### Quick Setup

1. **Ensure NightMend MCP Server is running** (default port 8003):
   ```bash
   docker compose up -d mcp
   ```

2. **Create/edit OpenCode config** at `~/.opencode/config.json`:
   ```json
   {
     "mcpServers": {
       "nightmend": {
         "type": "sse",
         "url": "http://<nightmend-host>:8003/sse",
         "headers": {
           "Authorization": "Bearer <your-mcp-api-key>"
         }
       }
     }
   }
   ```

   Replace `<nightmend-host>` with your server IP (e.g., `10.211.55.11`) and `<your-mcp-api-key>` with the value of `NIGHTMEND_MCP_API_KEY` from `.env`.

3. **Start OpenCode** and use natural language to interact with NightMend:
   ```
   $ opencode
   > Check the health of all servers
   > Show critical alerts from the last hour
   > Search error logs containing "connection refused"
   > Analyze alert 123 with full context
   ```

### Claude Code Integration

Claude Code also supports MCP. Add to `~/.claude/settings.json`:
```json
{
  "mcpServers": {
    "nightmend": {
      "type": "sse",
      "url": "http://<nightmend-host>:8003/sse",
      "headers": {
        "Authorization": "Bearer <your-mcp-api-key>"
      }
    }
  }
}
```

## Development

### Adding New Tools

1. **Define the tool function** in `app/mcp/server.py`:
   ```python
   @mcp_server.tool()
   def my_new_tool(param1: str, param2: int = 10) -> Dict[str, Any]:
       """Tool description for AI agents"""
       # Implementation
       return {"result": "data"}
   ```

2. **Test the tool:**
   ```bash
   python -m app.mcp.cli --verbose
   ```

3. **Update documentation** in this file

### Tool Design Principles

- **Clear parameter types** with defaults
- **Comprehensive error handling** 
- **Rich return data** with metadata
- **Focused functionality** (single responsibility)
- **Performance awareness** (use limits and time ranges)

## Troubleshooting

### Common Issues

1. **Database connection failed:**
   - Verify DATABASE_URL environment variable
   - Ensure PostgreSQL is running and accessible

2. **Import errors:**
   - Check Python path and working directory
   - Verify all dependencies are installed

3. **MCP client can't connect:**
   - Check server is running on correct host/port
   - Verify firewall settings
   - Check client configuration file syntax

### Debug Mode

Run with verbose logging to troubleshoot:
```bash
python -m app.mcp.cli --verbose --host 127.0.0.1 --port 8003
```

## Roadmap (P1 Extensions)

- `trigger_remediation`: Execute automated fixes
- `get_sla_status`: Check SLA compliance  
- `generate_report`: Create operational reports
- `manage_alerts`: Acknowledge/resolve alerts
- `deploy_service`: Infrastructure automation

## Security Considerations

- **Local access only** by default (127.0.0.1)
- **Database credentials** in environment variables
- **Bearer Token authentication** required in production via `NIGHTMEND_MCP_API_KEY` environment variable
- Production refuses to start without API key configured
- Development mode (`ENVIRONMENT=development`) allows unauthenticated access for local testing
- **Rate limiting** recommended for public exposure

## Marketing Message

> "NightMend: The first open-source monitoring platform with native MCP + AI analysis. Get intelligent operational insights through natural language."