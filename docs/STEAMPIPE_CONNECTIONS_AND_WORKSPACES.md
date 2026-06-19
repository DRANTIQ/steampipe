# Steampipe Connections and Workspaces — How We Configure AWS (and Other) Accounts

This document explains **Steampipe’s concepts** (connection, workspace, search path) and **how our platform configures and uses them** for AWS and other cloud accounts. It is informational only; no implementation steps.

---

## 1. What is a Steampipe **connection**?

In Steampipe:

- A **connection** = one configured data source for a **single plugin** (e.g. AWS, Azure, GCP).
- It has a **name** (e.g. `aws_prod`, `aws_397066be_0f11_448d_963e_6bc9a48b2dfe`).
- It is configured in **HCL** in a `.spc` file (e.g. `~/.steampipe/config/aws.spc`).
- Inside the Steampipe **database**, each connection is exposed as a **PostgreSQL schema** with the same name as the connection.
- The **scope** of a connection is plugin-specific:
  - **AWS**: one connection = one AWS account (optionally with regions, profile, or assume-role).
  - **Azure**: one connection = one subscription.
  - **GCP**: one connection = one project.

So: **one connection = one “client account” from the cloud provider’s point of view** (one AWS account, one Azure subscription, one GCP project). The plugin uses that connection’s config (credentials, regions, profile, etc.) to call the provider’s APIs and expose tables in that schema.

---

## 2. How we map **our** data to a Steampipe connection

In our platform:

- **CloudAccount** (DB) = one cloud account (tenant-scoped): provider, account_id, region, optional secret_arn, extra_metadata.
- For each **execution job** we have one **CloudAccount** and one **Query** (plugin + SQL).

We **synthesize one Steampipe connection per job**:

1. **Connection name**  
   We use a stable, unique name, e.g. `aws_<account_uuid>` (e.g. `aws_397066be_0f11_448d_963e_6bc9a48b2dfe`). This becomes the **Postgres schema name** Steampipe creates for that connection.

2. **Connection config (HCL)**  
   We build a single `connection "<name>" { ... }` block and write it to a **job-specific** `.spc` file (e.g. `config/aws.spc`) in a temp config dir for that run. The block contains:
   - `plugin = "aws"` (or the short plugin name).
   - Plugin-specific options, e.g. for AWS: `profile`, `regions`, and optionally `ignore_errors`, etc. We do **not** put `role_arn` / `external_id` in the connection block; for assume-role we handle that **outside** Steampipe (see below).

3. **Credentials**  
   - **Direct credentials**: We write `[default]` credentials (from env or Secrets Manager) to a file and set `AWS_SHARED_CREDENTIALS_FILE` and `AWS_PROFILE=default` so the AWS plugin uses that profile.
   - **Assume-role**: We call **STS AssumeRole** in our worker process, then write the **temporary** credentials to a file and pass that file (and profile) to Steampipe. So the plugin only ever sees the **assumed-role** credentials, not the master account keys.

So: **one execution job → one CloudAccount → one Steampipe connection** (one schema). We don’t persist connections in `~/.steampipe` long-term; we create a fresh config dir per job, run the query, then tear it down.

---

## 3. What is a Steampipe **workspace**?

In Steampipe:

- A **workspace** is a **named “profile”** for the Steampipe **client**: which database to use, cache settings, **search_path**, query options, etc.
- Workspaces are defined in `.spc` files (often `workspaces.spc`) under `~/.steampipe/config/`.
- You switch workspaces with `--workspace <name>` or `STEAMPIPE_WORKSPACE=<name>`.
- A workspace typically includes:
  - **install_dir** (where the Steampipe DB and plugins live),
  - **search_path** or **search_path_prefix** (which connections/schemas to use when you use **unqualified** table names),
  - cache, query timeout, output format, etc.

Important: **workspace = client-side context** (which DB, which search path, how to run queries). **Connection = server-side** (what schemas/tables exist in the DB and how they’re configured). The **database** (Steampipe service) loads **all** `.spc` files in its config dir and creates one schema per connection; the **client** (e.g. `steampipe query`) uses the workspace to know which DB to connect to and what search path to use.

---

## 4. How we use (or don’t use) workspaces

In our worker we **do not** define or switch workspaces by name. Instead we:

- Point Steampipe at a **job-specific config directory** (via `STEAMPIPE_CONFIG_DIR` and `STEAMPIPE_INSTALL_DIR`).
- That config dir contains:
  - **default.spc** – only `options "database" { port = ... }` (so the service listens on our chosen port).
  - **aws.spc** (or `<provider>.spc`) – the **single connection** for this job.
- We then run:
  ```bash
  steampipe query --output json --search-path <connection_name> "<query_text>"
  ```
- **`--search-path <connection_name>`** tells the Steampipe **client** for this one command: “when resolving unqualified table names, use this connection’s schema first.” So we get the same effect as “use this workspace’s search path” for that single query, without defining a named workspace.

So: **we don’t use workspace files or STEAMPIPE_WORKSPACE**. We use **one connection per job** and **explicit `--search-path`** to target that connection. The “workspace” is effectively implicit: one config dir, one connection, one search-path for the run.

---

## 5. **Search path** in depth

- In Postgres, the **search path** is an ordered list of **schemas**. When you use an **unqualified** table name (e.g. `SELECT * FROM aws_ec2_instance`), Postgres looks in each schema in order and uses the first table that matches.
- In Steampipe, **each connection = one schema**. So “search path” = “which connection(s) to use, and in what order,” when you don’t prefix the table with a schema name.

Examples:

- `search_path = aws_prod, aws_dev` → `SELECT * FROM aws_ec2_instance` hits `aws_prod.aws_ec2_instance` first.
- If you use a **qualified** name, e.g. `aws_dev.aws_ec2_instance`, the search path doesn’t matter for that table.

In our worker:

- We have **only one connection** in the config for that run (one AWS account).
- We pass **`--search-path <connection_name>`** so that the single connection we created is the one used for unqualified names. So every unqualified table in the query runs against that one AWS account’s schema.

We don’t use aggregators or multiple connections in one run; each job is strictly **one account, one connection, one search-path**.

---

## 6. End-to-end: from “AWS client account” to Steampipe

1. **Our model**  
   **CloudAccount** (and optional Secrets Manager / extra_metadata) defines the “AWS client account”: which account, which region(s), and whether we use direct creds or assume-role.

2. **Connection**  
   We build one `connection "<name>" { plugin = "aws"; profile = "default"; regions = ["us-east-1"]; ... }` in a job-specific `.spc` file. That connection is the Steampipe representation of that one AWS account.

3. **Credentials**  
   We write credentials (direct or assumed-role) to a file and set `AWS_SHARED_CREDENTIALS_FILE` / `AWS_PROFILE` so the AWS plugin uses them. The plugin then uses the AWS SDK (and thus GetCallerIdentity, etc.) with those credentials.

4. **Workspace**  
   We don’t create a workspace. We set **config dir** and **port** so the Steampipe service loads only our one connection and our database options.

5. **Search path**  
   We run `steampipe query --search-path <connection_name> "<query>"` so that the single connection we created is used for all unqualified table names.

6. **Service lifecycle**  
   We start `steampipe service start --foreground` with that config, wait for the service to be listening and for the connection to initialize (e.g. 10s), then run the query. After the job we stop the service and delete the temp config dir.

So: **we get the “connection” and “workspace-like” behavior (targeting one account) by (a) one connection in a dedicated config dir and (b) `--search-path` for that connection.** No named workspace file is required; the “workspace” is implicit in the config dir and the CLI search path for that run.

---

## 7. Summary table

| Concept        | Steampipe meaning | How we use it |
|----------------|-------------------|----------------|
| **Connection** | One data source (e.g. one AWS account) = one schema in the Steampipe DB. Configured in `.spc` with `connection "name" { plugin = "aws"; ... }`. | One connection per job; we generate the `.spc` with a unique name (e.g. `aws_<account_id>`) and plugin options (profile, regions). |
| **Workspace**  | Named client profile: which DB, search path, cache, etc. (often in `workspaces.spc`). | We don’t define workspaces. We emulate “use this one connection” via a dedicated config dir + `--search-path <connection_name>`. |
| **Search path**| Ordered list of schemas (connections) used to resolve unqualified table names. | We set it only for the single query: `--search-path <connection_name>` so the query runs against our single connection. |

---

## 8. Worker and Steampipe service lifecycle: one worker, one service per job

**One worker process does everything.** We do **not** run a separate worker (or Steampipe service) per connection and leave it up. We run a **single** long‑running worker process (e.g. one Docker container) that:

1. **Polls the queue** (Redis) in a loop.
2. **For each job** (one job = one connection for that run):
   - Builds a **job-specific config dir** (`run_<job_id>/`) with one connection and credentials.
   - **Stops** any existing Steampipe service (for this worker’s install dir).
   - **Starts** a **new** Steampipe service (`steampipe service start --foreground`) with that job’s config (one connection).
   - Waits for the service to listen and for the connection to initialize (~10s).
   - Runs **one** query (`steampipe query --search-path <connection_name> "..."`).
   - In a `finally` block: **terminates** the Steampipe service process and runs `steampipe service stop`, then deletes the job’s config dir.

So:

- **Worker**: **one** process handles all jobs, one job at a time (no parallelism inside a single worker).
- **Steampipe service**: **one** service at a time per worker; it is **started for a job** and **stopped after that job**. The next job gets a fresh service start with the next job’s connection.
- **Connection**: Each job gets its own connection config and its own short‑lived Steampipe service instance; there is no long‑lived “one service per connection.”

To run multiple jobs in parallel you run **multiple worker processes** (e.g. multiple containers or processes), each with the same loop; each still does “start service for this job → query → stop service” for its own job.

---

If you want to go deeper, the official docs are the source of truth:

- [Managing Connections](https://steampipe.io/docs/managing/connections)
- [Workspace config](https://steampipe.io/docs/reference/config-files/workspace)
- [Using search_path](https://steampipe.io/docs/guides/search-path)
