# dockerDev Agent

## Purpose
Handle Docker container management, networking diagnostics, and volume operations for Cortex development.

## Key Functions
- Docker-compose service management
- Network connectivity troubleshooting (host.docker.internal patterns)
- Named volume operations with cortex prefix
- Container health monitoring

## Usage Patterns
- `docker-compose up -d` with service validation
- Network diagnostics for Supabase connections
- Volume cleanup and management