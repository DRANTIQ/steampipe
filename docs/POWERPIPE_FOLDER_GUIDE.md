# Powerpipe Folder — What It Is and How It Works

This doc explains the **`powerpipe/`** folder in this project: what Powerpipe is, what’s in the folder, and how the pieces fit together.

---

## 1. What is Powerpipe?

**Powerpipe** is the tool from Turbot for running **benchmarks** and **dashboards** on top of **Steampipe**. Steampipe gives you SQL over cloud APIs (e.g. `aws_ec2_instance`); Powerpipe adds:

- **Benchmarks** – Groups of **controls** (checks) you can run (e.g. “SOC 2”, “CIS AWS”).
- **Controls** – Single checks: each runs a **query** (SQL) and is marked **pass** or **fail** depending on the result.
- **Mods** – HCL “modules” that define benchmarks, controls, variables, and (optionally) dashboards.
- **Dashboards** – UI (e.g. `powerpipe server`) to run benchmarks and view results.

So: **Steampipe** = SQL over cloud; **Powerpipe** = benchmarks + controls + dashboards built on that SQL.

---

## 2. What’s in the `powerpipe/` folder?

Two main parts:

### 2.1 Your local mod: `mod.pp` (root)

```hcl
mod "local" {
  title = "powerpipe"
  require {
    mod "github.com/turbot/steampipe-mod-aws-compliance" {
      version = "*"
    }
  }
}
```

- Defines a **local mod** named `"local"` with title `"powerpipe"`.
- **Requires** (depends on) the Turbot **AWS Compliance** mod from GitHub; `version = "*"` means “any version.”
- When you run Powerpipe here (e.g. `powerpipe benchmark run`), it loads this mod and pulls in the AWS Compliance mod.

So this folder is a **thin wrapper**: it doesn’t define its own benchmarks; it just pulls in the full AWS compliance mod.

### 2.2 Resolved dependency: `.powerpipe/mods/`

After you run Powerpipe (e.g. `powerpipe mod install` or `powerpipe benchmark run`), dependencies are downloaded under:

- **`.powerpipe/mods/github.com/turbot/steampipe-mod-aws-compliance@v1.13.0/`**

That directory is the **AWS Compliance mod** at version v1.13.0. It contains:

| Content | What it is |
|--------|------------|
| **mod.pp** | Mod metadata: title, description, `database = var.database`, `require { plugin "aws" }`. |
| **variables.pp** | Variables (e.g. `common_dimensions`, `tag_dimensions`, `database` connection). |
| **powerpipe.ppvars.example** | Example variable values (dimensions, Lambda runtimes, etc.). |
| **Benchmark folders** (e.g. **soc_2/**, **foundational_security/**, **rbi_cyber_security/**, **pci_dss_v40/**, **rbi_itf_nbfc/**) | One or more `.pp` files per framework. |
| **docs/** (inside benchmarks) | Markdown docs for each benchmark/control. |

So the **actual** benchmarks and controls live inside the **AWS Compliance** mod under `.powerpipe/mods/`, not in your root `mod.pp`.

---

## 3. How benchmarks and controls are structured

### 3.1 Hierarchy

- A **benchmark** is a group of **controls** and/or **child benchmarks**.
- Controls are the leaves: each control runs **one query** and passes or fails.

Example from the mod:

- **benchmark "soc_2"** (top-level: “AWS SOC 2”)
  - **benchmark "soc_2_cc_1"** (section CC1)
    - **benchmark "soc_2_cc_1_3"** (subsection CC1.3)
      - **control** `iam_group_not_empty`, `iam_user_in_group`, … (each runs a query)
  - **benchmark "soc_2_cc_2"**
    - …

### 3.2 What a benchmark block looks like (HCL)

```hcl
benchmark "soc_2" {
  title         = "AWS SOC 2"
  description   = "System and Organization Controls (SOC) 2..."
  documentation = file("./soc_2/docs/soc_2_overview.md")
  children = [
    benchmark.soc_2_cc_1,
    benchmark.soc_2_cc_2,
    ...
  ]
  tags = local.soc_2_common_tags
}
```

- **children** = list of child benchmarks (or controls in deeper levels).
- **tags** = labels (e.g. compliance framework, section id) for filtering and grouping.

### 3.3 What a control block looks like (HCL)

```hcl
control "foundational_security_s3_1" {
  title         = "1 S3 Block Public Access setting should be enabled"
  description   = "This control checks whether..."
  severity      = "medium"
  query         = query.s3_public_access_block_account
  documentation = file("./foundational_security/docs/foundational_security_s3_1.md")
  tags = merge(local.foundational_security_s3_common_tags, { ... })
}
```

- **query** = reference to a **query** resource (SQL). Rows returned = failures; no rows = pass.
- **severity** = critical / high / medium / low (for reporting).
- **tags** = which frameworks/sections this control belongs to.

### 3.4 Queries

- Controls point to **query** resources (e.g. `query.s3_public_access_block_account`, `query.vpc_flow_logs_enabled`).
- Those **query** blocks live in the same AWS Compliance mod; they contain the **SQL** that runs against Steampipe (AWS plugin) tables.
- So: **control** = one compliance check; **query** = the SQL that implements that check.

---

## 4. Frameworks in the AWS Compliance mod (examples)

From the folder layout, the mod includes (among others):

- **soc_2** – SOC 2 (e.g. CC1, CC2, …, A1, C1).
- **foundational_security** – AWS Foundational Security Best Practices (by service: S3, RDS, WAF, SSM, etc.).
- **rbi_cyber_security** – RBI Cyber Security Framework (Annex I, etc.).
- **rbi_itf_nbfc** – RBI IT Framework for NBFC.
- **pci_dss_v40** – PCI DSS v4.0 (e.g. requirement_8).
- **conformance_pack** – Conformance-pack style controls (e.g. VPC, WAF).

Each is a set of benchmarks and controls; all use the same **AWS** Steampipe plugin and **variables** (e.g. `common_dimensions`, `database`).

---

## 5. Variables and configuration

- **variables.pp** in the AWS Compliance mod defines things like:
  - **common_dimensions** – e.g. `["account_id", "region"]` added to control results.
  - **tag_dimensions** – optional tag names for dimensions.
  - **database** – Steampipe database connection (defaults to `connection.steampipe.default`).
- You can override these with a **powerpipe.ppvars** file (or `.auto.powerpipe.ppvars`) in your mod directory; **powerpipe.ppvars.example** shows the shape.

So the **powerpipe/** folder uses the AWS Compliance mod’s variables; you can tune them via `.ppvars` in the `powerpipe/` directory if needed.

---

## 6. How this relates to the rest of the project

- **This repo’s API/worker** runs **Steampipe queries** (raw SQL) per job and stores results; it does **not** run Powerpipe benchmarks.
- The **powerpipe/** folder is for **running Powerpipe locally** (or in a separate flow): you’d run `powerpipe benchmark run` (or `powerpipe server`) from the `powerpipe/` directory, with a Steampipe service and AWS connection already configured.
- If you later want the **platform** to run Powerpipe benchmarks (e.g. “run SOC 2 for this account”), you’d add jobs that invoke **Powerpipe** (e.g. `powerpipe benchmark run soc_2 --export json`) instead of (or in addition to) raw `steampipe query`; the powerpipe folder and this doc describe **what** those benchmarks are and **how** they’re defined.

---

## 7. Quick reference

| Item | Location | Purpose |
|------|----------|---------|
| Your mod | `powerpipe/mod.pp` | Declares local mod and requires `steampipe-mod-aws-compliance`. |
| AWS Compliance mod | `powerpipe/.powerpipe/mods/.../steampipe-mod-aws-compliance@v1.13.0/` | All benchmarks, controls, queries, variables, docs. |
| Benchmarks | `*/**/*.pp` under that mod (e.g. `soc_2/soc_2.pp`, `foundational_security/s3.pp`) | Groups of controls/sections. |
| Controls | Same `.pp` files | Single checks; each references a `query.*`. |
| Queries | Same mod (e.g. in `queries/` or embedded) | SQL run by controls. |
| Variables | `variables.pp`, `powerpipe.ppvars.example` | Dimensions, database, options. |

---

## 8. Useful commands (run from `powerpipe/`)

- **Install/update mod deps:** `powerpipe mod install`
- **List benchmarks:** `powerpipe benchmark list`
- **Run one benchmark:** `powerpipe benchmark run soc_2` (or another benchmark name)
- **Run with Steampipe connection:** Use `--search-path` or set connection in Steampipe config so the mod’s queries run against the right AWS connection.
- **Start UI:** `powerpipe server` (then run benchmarks from the UI).

(Requires Powerpipe and Steampipe installed, and a running Steampipe service with AWS connection configured.)

---

This folder is your **Powerpipe workspace** that pulls in the full **AWS Compliance** mod so you can run and understand compliance benchmarks (SOC 2, Foundational Security, RBI, PCI, etc.) on top of Steampipe’s AWS data.
