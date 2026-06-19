# Plugin Tables Reference — Context for the Team

This doc explains the **plugin tables** documentation in this repo: what those tables are, how they fit into Steampipe and our platform, and how to use them when writing or understanding queries.

---

## 1. What are “plugin tables”?

In **Steampipe**, each **plugin** (e.g. AWS, Azure, GCP) exposes cloud resources as **SQL tables** inside a Postgres-compatible database. For example:

- **`aws_ec2_instance`** – EC2 instances (like `aws ec2 describe-instances`).
- **`aws_s3_bucket`** – S3 buckets.
- **`aws_dynamodb_table`** – DynamoDB tables.
- **`aws_vpc_subnet`**, **`aws_vpc_security_group`** – VPC resources.
- Hundreds more for other AWS services (IAM, RDS, Lambda, etc.).

When our **worker** runs a Steampipe query, it executes **SQL against these tables**. The SQL you store in the **Query** model (e.g. `select * from aws_ec2_instance limit 10`) uses these table names and columns. The plugin turns that SQL into API calls to AWS and returns rows.

So: **plugin tables = the list of “tables” you can use in SQL when writing queries for this platform.** Each table maps to a type of AWS (or other cloud) resource.

---

## 2. Where are the table docs in this repo?

We’ve copied the **Steampipe AWS plugin table documentation** from the Steampipe Hub into the repo so the team has a local reference.

**Location:**  
`plugins/hub.steampipe.io/plugins/turbot/aws@latest/docs/tables/`

**Contents:**  
One Markdown file per table (see counts below).

**Source:**  
These are the same docs you’d see on [Steampipe Hub → AWS plugin → Tables](https://hub.steampipe.io/plugins/turbot/aws/tables). Keeping them in the repo lets everyone understand table context without leaving the codebase.

---

## 3. How many tables, and how many per service?

**Total AWS plugin tables in this repo:** **578**

Tables are grouped below by **service** (the first segment after `aws_` in the table name, e.g. `aws_ec2_instance` → **ec2**). Each row is one AWS service area; the number is how many tables (table docs) we have for that service.

| # Tables | Service |
|----------|---------|
| 39 | ec2 |
| 28 | vpc |
| 27 | rds |
| 18 | iam |
| 16 | cost |
| 15 | cloudwatch |
| 14 | wellarchitected |
| 14 | elasticache |
| 13 | api |
| 12 | ssm |
| 11 | route53 |
| 10 | securityhub |
| 10 | glue |
| 9 | lambda |
| 9 | backup |
| 8 | s3 |
| 8 | emr |
| 8 | eks |
| 8 | ecs |
| 8 | ebs |
| 7 | shield |
| 7 | quicksight |
| 7 | organizations |
| 7 | guardduty |
| 7 | config |
| 7 | cloudtrail |
| 6 | sagemaker |
| 6 | redshift |
| 6 | dynamodb |
| 6 | cloudfront |
| 6 | bedrock |
| 5 | ssoadmin |
| 5 | inspector2 |
| 5 | inspector |
| 5 | codebuild |
| 5 | auditmanager |
| 4 | wafv2, waf, servicequotas, servicecatalog, resource, kinesis, iot, ecr, drs, dms, dax, cognito |
| 3 | wafregional, transfer, sns, sfn, ses, service, s3tables, networkfirewall, lakeformation, kms, identitystore, globalaccelerator, elastic, efs, docdb, directory, codedeploy, cloudformation, account |
| 2 | workspaces, trusted, timestreamwrite, securitylake, rolesanywhere, redshiftserverless, ram, pricing, opensearch, oam, neptune, msk, macie2, lightsail, keyspaces, health, fms, eventbridge, connect, codeartifact, ce, athena, appsync, appstream, appautoscaling, accessanalyzer |
| 1 | tagging, sts, ssmincidents, sqs, simspaceweaver, sesv2, serverlessapplicationrepository, secretsmanager, scheduler, savingsplans, region, pipes, pinpoint, mskconnect, mq, mgn, memorydb, media, kinesisanalyticsv2, glacier, fsx, elasticsearch, ecrpublic, dlm, datasync, costoptimizationhub, codestar, codepipeline, codecommit, cloudsearch, cloudcontrol, budgets, batch, availability, appconfig, app, amplify, acmpca, acm |

So when you write a query, you’re choosing one of these 578 tables (and optionally joining across services). The table doc for that name (e.g. `aws_ec2_instance.md`) describes columns and example queries.

---

## 4. What’s in each table doc?

Each `*.md` file typically includes:

| Section | Purpose |
|--------|----------|
| **Title / description** | Table name and short summary of what it represents (e.g. “DynamoDB tables”, “EC2 instances”). |
| **Table usage guide** | What the table is for, which AWS resource it maps to, and how you can use it (e.g. “query table-specific details, including provisioned throughput, encryption status”). |
| **Columns / schema** | (If present) Column names and types so you know what to `SELECT` or `WHERE` on. |
| **Examples** | Example SQL queries (e.g. “list unencrypted DynamoDB tables”, “list S3 buckets with public access”). Often in both Postgres and SQLite variants; we run Postgres-style. |

Use these docs to:

- **Choose the right table** for what you want to query (e.g. `aws_ec2_instance` for instances, `aws_s3_bucket` for buckets).
- **See which columns exist** and how they’re used in examples.
- **Copy or adapt example queries** when creating **Query** records or ad‑hoc Steampipe SQL.

---

## 5. How this fits into our platform

| Our concept | How it uses plugin tables |
|-------------|----------------------------|
| **Query** (DB model) | Stores `query_text` (SQL). That SQL references **plugin tables** (e.g. `aws_ec2_instance`, `aws_s3_bucket`). The table must exist in the plugin for the connection (e.g. AWS) you run the query against. |
| **Execution job** | One job = one **account** + one **query**. The worker runs that query against the Steampipe **connection** for that account; Steampipe executes the SQL against the **plugin tables** in that connection’s schema. |
| **Snapshot / result** | The query result (rows from the plugin tables) is stored as the execution snapshot (e.g. JSON in S3 or local path). |

So:

- **Plugin tables** = the “data model” your SQL talks to.
- **Table docs** in `plugins/.../docs/tables/` = reference for that data model so the team can write and understand queries.

---

## 6. How to use the tables section

- **When adding or editing a Query (e.g. in API or DB):**  
  - Pick the right **plugin** (e.g. `aws`) and **table** (e.g. `aws_ec2_instance`).  
  - Open the corresponding `plugins/.../docs/tables/<table_name>.md` to see columns and example SQL.  
  - Use or adapt the examples as `query_text`.

- **When debugging or interpreting execution results:**  
  - Look at the **query_text** of the Query that was run.  
  - Find the table(s) it uses (e.g. `aws_dynamodb_table`) and open that table’s doc to understand what the result rows represent (e.g. “each row is one DynamoDB table with these attributes”).

- **When designing bulk or compliance checks:**  
  - Use the table docs to see what’s available per service (e.g. encryption, backup, public access).  
  - Combine with the **Powerpipe** mod (see `docs/POWERPIPE_FOLDER_GUIDE.md`) if you want to run full benchmarks; for single ad‑hoc checks, writing SQL against these tables is enough.

---

## 7. Quick reference: table naming

- **AWS plugin:** Table names usually follow `aws_<service>_<resource>` or `aws_<service>_<resource>_<subresource>`, e.g.:
  - `aws_ec2_instance`
  - `aws_s3_bucket`
  - `aws_dynamodb_table`
  - `aws_vpc_subnet`, `aws_vpc_security_group`, `aws_vpc_route_table`
  - `aws_iam_user`, `aws_iam_role`, `aws_iam_policy`
- **Connection / schema:** In our worker we run with one connection per job (e.g. `aws_<account_id>`). Your SQL typically uses **unqualified** table names (e.g. `aws_ec2_instance`); Steampipe resolves them using the connection’s search path.

---

## 8. Summary

| What | Where | Why |
|------|--------|-----|
| **Plugin tables** | Steampipe AWS (and other) plugins | They are the SQL interface to cloud resources; our queries run against them. |
| **Table docs (this repo)** | `plugins/hub.steampipe.io/plugins/turbot/aws@latest/docs/tables/*.md` | Local reference so the team understands table purpose, columns, and example queries. |
| **Usage** | When defining Query `query_text`, debugging results, or designing checks | Pick the right table, write correct SQL, interpret snapshot rows. |

The **tables section** in the repo is the copied Steampipe AWS plugin table documentation; use it as the shared reference for **which tables exist** and **how to query them** in this platform.
