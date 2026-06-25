# adapter-mcp.ps1 — MCP tool discovery and capability listing
# Scans available MCP tools from environment and generates quick-reference
# Usage:
#   adapter-mcp.ps1 -List                     → list all MCP tools by server
#   adapter-mcp.ps1 -Search <keyword>         → find tools matching keyword
#   adapter-mcp.ps1 -Server <name>            → list tools from one server
#   adapter-mcp.ps1 -QuickRef                 → generate quick-reference card
#   adapter-mcp.ps1 -Stats                    → usage statistics (if available)
param([switch]$List, [string]$Search, [string]$Server, [switch]$QuickRef, [switch]$Stats)

$ErrorActionPreference = "Continue"

# MCP tool catalog — initialized in a function to avoid script-top parsing issues
function Get-McpCatalog {
    $catalog = @{}
    $catalog["comfyui"] = @{
        description = "ComfyUI Stable Diffusion workflow management"
        tools = @(
            @{name="generate_image"; desc="Generate image from text prompt"; category="generation"},
            @{name="enqueue_workflow"; desc="Submit workflow for execution"; category="execution"},
            @{name="get_job_status"; desc="Check job execution status"; category="monitor"},
            @{name="get_history"; desc="Get execution history with outputs"; category="monitor"},
            @{name="list_local_models"; desc="List installed model files"; category="inventory"},
            @{name="search_models"; desc="Search HuggingFace for models"; category="discovery"},
            @{name="download_model"; desc="Download model from URL"; category="install"},
            @{name="install_custom_node"; desc="Install custom node pack"; category="install"},
            @{name="get_workflow"; desc="Load saved workflow JSON"; category="workflow"},
            @{name="save_workflow"; desc="Save workflow to user library"; category="workflow"},
            @{name="validate_workflow"; desc="Validate without executing"; category="workflow"},
            @{name="analyze_workflow"; desc="Analyze workflow structure"; category="workflow"},
            @{name="get_system_stats"; desc="GPU/VRAM/system info"; category="monitor"},
            @{name="start_comfyui"; desc="Start ComfyUI process"; category="control"},
            @{name="stop_comfyui"; desc="Stop ComfyUI process"; category="control"},
            @{name="restart_comfyui"; desc="Restart ComfyUI process"; category="control"},
            @{name="upload_image"; desc="Upload image to input dir"; category="io"},
            @{name="view_image"; desc="View generated image inline"; category="io"},
            @{name="get_image"; desc="Download generated image"; category="io"},
            @{name="get_logs"; desc="Get server runtime logs"; category="debug"}
        )
    }
$catalog["memory"] = @{
        description = "Knowledge graph persistent memory"
        tools = @(
            @{name="create_entities"; desc="Create KG entities"; category="write"},
            @{name="add_observations"; desc="Add observations to entities"; category="write"},
            @{name="create_relations"; desc="Create relations between entities"; category="write"},
            @{name="search_nodes"; desc="Search KG by query"; category="read"},
            @{name="open_nodes"; desc="Open specific entities by name"; category="read"},
            @{name="read_graph"; desc="Read entire knowledge graph"; category="read"},
            @{name="delete_entities"; desc="Delete entities and relations"; category="write"},
            @{name="delete_observations"; desc="Delete specific observations"; category="write"},
            @{name="delete_relations"; desc="Delete relations"; category="write"}
        )
    }
$catalog["gigs-sh"] = @{
        description = "Agent gig economy platform directory"
        tools = @(
            @{name="search_gigs"; desc="Search platform listings"; category="discovery"},
            @{name="get_gig"; desc="Get full listing details"; category="read"},
            @{name="list_categories"; desc="List platform categories"; category="read"},
            @{name="find_by_agent_welcomed"; desc="Filter by agent-welcomed"; category="discovery"},
            @{name="find_by_onboarding_friction"; desc="Filter by onboarding difficulty"; category="discovery"},
            @{name="find_by_payment_rail"; desc="Filter by payment method"; category="discovery"},
            @{name="find_by_agent_allowed"; desc="Filter by agent-allowed status"; category="discovery"}
        )
    }
$catalog["context7"] = @{
        description = "Up-to-date library documentation"
        tools = @(
            @{name="resolve-library-id"; desc="Find Context7 library ID"; category="discovery"},
            @{name="query-docs"; desc="Query library documentation"; category="read"}
        )
    }
$catalog["sequential-thinking"] = @{
        description = "Structured reasoning tool"
        tools = @(
            @{name="sequentialthinking"; desc="Multi-step reflective thinking"; category="reasoning"}
        )
    }
    return $catalog
}

$McpCatalog = Get-McpCatalog

# ── List ──
if ($List) {
    foreach ($serverName in $McpCatalog.Keys | Sort-Object) {
        $server = $catalog[$serverName]
        Write-Output "`n═══ $serverName — $($server.description) ═══"
        foreach ($cat in ($server.tools | Group-Object category | Sort-Object Name)) {
            Write-Output "  [$($cat.Name)]"
            foreach ($t in $cat.Group) {
                Write-Output "    $($t.name.PadRight(28)) $($t.desc)"
            }
        }
    }
    Write-Output "`nTotal: $(($McpCatalog.Values | ForEach-Object { $_.tools.Count } | Measure-Object -Sum).Sum) tools across $($McpCatalog.Count) servers"
    exit 0
}

# ── Search ──
if ($Search) {
    $found = @()
    foreach ($serverName in $McpCatalog.Keys) {
        foreach ($t in $catalog[$serverName].tools) {
            if ($t.name -match $Search -or $t.desc -match $Search) {
                $found += @{ server = $serverName; name = $t.name; desc = $t.desc; category = $t.category }
            }
        }
    }
    if ($found.Count -eq 0) { Write-Output "No MCP tools match '$Search'"; exit 0 }
    Write-Output "MCP tools matching '$Search' ($($found.Count) found):"
    foreach ($f in $found) { Write-Output "  [$($f.server)] $($f.name) — $($f.desc) ($($f.category))" }
    exit 0
}

# ── Server ──
if ($Server) {
    if (-not $catalog[$Server]) { Write-Output "Unknown server: $Server. Known: $($McpCatalog.Keys -join ', ')"; exit 1 }
    $s = $catalog[$Server]
    Write-Output "$Server`: $($s.description) ($($s.tools.Count) tools)"
    foreach ($t in $s.tools) { Write-Output "  $($t.name) — $($t.desc) [$($t.category)]" }
    exit 0
}

# ── QuickRef ──
if ($QuickRef) {
    Write-Output @"

╔══════════════════════════════════════════════════════════════╗
║                    MCP TOOL QUICK REFERENCE                   ║
╠══════════════════════════════════════════════════════════════╣
║ comfyui (20)     — Image gen, workflows, models              ║
║ memory  (9)      — Knowledge graph CRUD                      ║
║ gigs-sh (7)      — Agent platform directory                  ║
║ context7 (2)     — Library documentation                     ║
║ sequential (1)   — Structured reasoning                      ║
╠══════════════════════════════════════════════════════════════╣
║ Most-used patterns:
║   Generate: generate_image → get_job_status → view_image
║   Memory:  search_nodes → open_nodes → create_entities
║   Discover: search_gigs → get_gig
║   Docs:     resolve-library-id → query-docs
║   Debug:    get_logs → get_system_stats → restart_comfyui
╚══════════════════════════════════════════════════════════════╝

"@
    exit 0
}

# ── Stats ──
if ($Stats) {
    Write-Output "MCP Tool Statistics:"
    Write-Output "  Total servers: $($McpCatalog.Count)"
    Write-Output "  Total tools: $(($McpCatalog.Values | ForEach-Object { $_.tools.Count } | Measure-Object -Sum).Sum)"
    Write-Output ""
    foreach ($serverName in $McpCatalog.Keys | Sort-Object) {
        $s = $catalog[$serverName]
        $reads = ($s.tools | Where-Object { $_.category -in @("read","discovery","monitor","inventory") }).Count
        $writes = ($s.tools | Where-Object { $_.category -in @("write","install","execution","control") }).Count
        Write-Output "  $serverName`: $($s.tools.Count) total (${reads}R/${writes}W)"
    }
    exit 0
}

# Default: show overview
Write-Output "MCP Tool Catalog: $($McpCatalog.Count) servers, $(($McpCatalog.Values | ForEach-Object { $_.tools.Count } | Measure-Object -Sum).Sum) tools"
Write-Output "Use -List, -Search <kw>, -Server <name>, -QuickRef, or -Stats"
