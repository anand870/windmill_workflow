# Windmill Development Environment

A Docker Compose setup for Windmill with PostgreSQL, Redis, server, and worker services. Flows and scripts are tracked in Git and can be replicated on any system with a single push.

## Prerequisites

- Docker (v20.10+)
- Docker Compose (v2.0+)
- Node.js (for `wmill` CLI) — `npm install -g windmill-cli`
- macOS, Linux, or Windows with WSL2

## Quick Start

### 1. Start the Environment

```bash
docker-compose up -d
```

### 2. Access Windmill

```
http://localhost:8000
```

Default credentials: `admin@windmill.dev` / `changeme`

### 3. Connect the CLI

```bash
# Add the workspace profile (one-time per machine)
wmill workspace add rohit rohit http://localhost:8000 --token <YOUR_TOKEN>
```

Get a token from **Settings → Tokens** in the Windmill UI, or via the API:

```bash
curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@windmill.dev", "password": "changeme"}' \
  | xargs -I{} curl -s -X POST http://localhost:8000/api/users/tokens/create \
    -H "Authorization: Bearer {}" \
    -H "Content-Type: application/json" \
    -d '{"label": "CLI token"}'
```

### 4. Push Flows to the Workspace

```bash
wmill sync push --workspace rohit --yes
```

---

## Replicating on a New System

Clone the repo, start Docker, connect the CLI, and push — all flows and scripts are restored automatically.

```bash
git clone <repo-url>
cd workflow

# Start Windmill
docker-compose up -d

# Install CLI
npm install -g windmill-cli

# Connect to the workspace (use your token — see step 3 above)
wmill workspace add rohit rohit http://localhost:8000 --token <YOUR_TOKEN>

# Deploy all flows and scripts
wmill sync push --workspace rohit --yes
```

---

## Folder Structure

```
.
├── docker-compose.yml                    # Windmill infrastructure
├── .env                                  # Local env vars (gitignored)
├── wmill.yaml                            # wmill CLI config (workspace, sync rules)
├── wmill-lock.yaml                       # Dependency hashes for reproducibility
├── f/                                    # Windmill flows and scripts (committed to git)
│   └── examples/
│       └── math_expression__flow/
│           ├── flow.yaml                 # Flow definition (steps, schema)
│           ├── step1_add.ts              # Step 1: a + b
│           ├── step2_multiply.ts         # Step 2: (a+b) * a
│           └── step3_add_b.ts            # Step 3: result + b
├── data/                                 # Persistent volumes (gitignored)
│   ├── postgres/
│   ├── redis/
│   └── windmill/
└── scripts/                              # Utility scripts
```

---

## Flows

### `f/examples/math_expression`

Computes `(((a+b)*a)+b)` across three sequential steps.

**Inputs:** `a` (number), `b` (number)

| Step | Operation | Expression |
|------|-----------|------------|
| `step1_add` | Add inputs | `a + b` |
| `step2_multiply` | Multiply by a | `(a+b) * a` |
| `step3_add_b` | Add b | `((a+b)*a) + b` |

**Example:** `a=3, b=2` → `(((3+2)×3)+2)` = **17**

**Preview locally (no deploy):**
```bash
wmill flow preview f/examples/math_expression__flow --workspace rohit -d '{"a": 3, "b": 2}'
```

---

## CLI Reference

```bash
# Preview a flow locally without deploying
wmill flow preview f/examples/math_expression__flow --workspace rohit -d '{"a": 3, "b": 2}'

# Push local changes to workspace
wmill sync push --workspace rohit --yes

# Pull workspace state to local files
wmill sync pull --workspace rohit --yes

# Regenerate lock files after editing inline scripts
wmill generate-metadata --workspace rohit --yes
```

---

## Adding a New Flow

```bash
# Scaffold a new flow
wmill flow new f/examples/my_flow --summary "What this flow does"

# Edit f/examples/my_flow__flow/flow.yaml and add inline .ts scripts
# Then push
wmill sync push --workspace rohit --yes
```

The flow files are plain YAML + TypeScript — commit them to git and they can be replicated anywhere.

---

## Configuration

All settings are in `.env` (gitignored — copy from `.env.example` if present):

| Variable | Default | Description |
|----------|---------|-------------|
| `WINDMILL_PORT` | `8000` | Windmill UI/API port |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `REDIS_PORT` | `6379` | Redis port |
| `JWT_SECRET` | *(change this)* | Auth secret — must be changed in production |
| `NUM_WORKERS` | `2` | Number of job workers |

---

## Common Commands

```bash
# Start all services
docker-compose up -d

# Stop services
docker-compose down

# View logs
docker-compose logs -f windmill

# Stop and wipe all data
docker-compose down -v   # ⚠️ destructive

# Access the database
docker-compose exec postgres psql -U windmill -d windmill
```

---

## Troubleshooting

**Port already in use:** Change `WINDMILL_PORT`, `POSTGRES_PORT`, or `REDIS_PORT` in `.env`.

**Worker not processing jobs:**
```bash
docker-compose logs windmill_worker
```

**Services won't start:**
```bash
docker-compose pull && docker-compose up -d
```

**Sync conflicts:** Run `wmill sync pull --workspace rohit` first to reconcile remote state, then push.

---

## Production Checklist

- [ ] Set a strong `JWT_SECRET` in `.env`
- [ ] Use strong `DATABASE_PASSWORD` and `REDIS_PASSWORD`
- [ ] Use managed PostgreSQL and Redis (not Docker volumes)
- [ ] Configure SSL/TLS
- [ ] Set up automated backups
- [ ] Restrict network access (firewall, security groups)

---

## Resources

- [Windmill Documentation](https://docs.windmill.dev)
- [Windmill CLI Reference](https://docs.windmill.dev/docs/advanced/cli)
- [Docker Compose Documentation](https://docs.docker.com/compose)
