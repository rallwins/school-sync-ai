# ADR 0005: Local-first storage, optional low-cost cloud demo

Status: accepted.

**Decision.** SQLite with portable SQL migrations (`backend/migrations/`) behind a small `Store`
class, so PostgreSQL can replace it later. Local run needs only Python and Node.

The public demo runs the same container on AWS Lambda behind a Function URL, with a Vercel frontend
that proxies `/api` and adds a shared key server-side. The account is on the AWS Paid plan with no
credits, so Lambda (always-free allowance) was chosen over EC2/App Runner/ALB/Fargate, which would
bill immediately. Fargate + ALB + Secrets Manager remains the documented production shape.

**Consequences.** On Lambda, SQLite lives in `/tmp` and resets, so the demo is for synthetic data
only and import history/manifest are not durable there. Concurrency cannot be pinned (quota 10), so
a preview and confirm may hit different instances; the plan-token check rejects that with 409.
Durable hosting needs RDS/Aurora or a persistent volume, plus a real secret store and auth.
