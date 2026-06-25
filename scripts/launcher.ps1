$env:ANTHROPIC_BASE_URL            = "https://api.deepseek.com/anthropic"
$env:ANTHROPIC_AUTH_TOKEN          = "sk-b395615ed9424e178a1a1c9ef3499310"
$env:ANTHROPIC_MODEL               = "deepseek-v4-pro"
$env:ANTHROPIC_DEFAULT_OPUS_MODEL   = "deepseek-v4-pro"
$env:ANTHROPIC_DEFAULT_SONNET_MODEL = "deepseek-v4-pro"
$env:ANTHROPIC_DEFAULT_HAIKU_MODEL  = "deepseek-v4-flash"
$env:CLAUDE_CODE_SUBAGENT_MODEL     = "deepseek-v4-flash"
cd $env:USERPROFILE\.claude
claude
