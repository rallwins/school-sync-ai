# AWS demo deployment (Lambda + Function URL)

Deployed 2026-10-24 to an AWS account (id omitted here), us-east-1, stack `schoolsync-demo`, with the
Vercel frontend at https://schoolsync-ai.vercel.app. Synthetic data only.

```
Browser -> Vercel (Next.js) -> /api proxy route (adds X-API-Key) -> Lambda Function URL -> FastAPI
```

Why Lambda: the account is on the AWS **Paid plan with $0 credits**, so EC2/App Runner/ALB would
bill from the first hour. Lambda's always-free allowance (1M requests, 400k GB-s per month)
applies regardless of plan.

## Resources (all in `template.yaml`)
ECR repo `schoolsync-backend` (keeps 2 images), Lambda `schoolsync-backend` (1024 MB, 30 s,
container image), public Function URL, logs-only IAM role, log group (14-day retention),
budget `schoolsync-demo-monthly` ($5, emails at 80% actual / 100% forecast).

## Redeploy
```powershell
$account = aws sts get-caller-identity --profile freetier --query Account --output text
$repo = "$account.dkr.ecr.us-east-1.amazonaws.com/schoolsync-backend"
aws ecr get-login-password --profile freetier --region us-east-1 | docker login --username AWS --password-stdin "$account.dkr.ecr.us-east-1.amazonaws.com"
docker build --provenance=false --platform linux/amd64 -f backend/Dockerfile.lambda -t ${repo}:v2 backend
docker push ${repo}:v2
aws cloudformation deploy --profile freetier --region us-east-1 --stack-name schoolsync-demo `
  --template-file infra/aws/template.yaml --capabilities CAPABILITY_IAM `
  --parameter-overrides ApiKey=(Get-Content .deploy/api_key.txt) BudgetEmail=<your-email> ImageUri=${repo}:v2
```
`.deploy/api_key.txt` is git-ignored. The same key must be the Vercel `BACKEND_API_KEY`.

## Teardown (removes everything above)
```powershell
aws ecr batch-delete-image --profile freetier --region us-east-1 --repository-name schoolsync-backend --image-ids "$(aws ecr list-images --profile freetier --region us-east-1 --repository-name schoolsync-backend --query 'imageIds[*]' --output json)"
aws cloudformation delete-stack --profile freetier --region us-east-1 --stack-name schoolsync-demo
```
(Delete images first: a non-empty ECR repository blocks stack deletion.) Remove the Vercel
project with `npx vercel remove schoolsync-ai` from `frontend/`.

## Known limits
- **Cold start ~20 s** on the first request after idle (measured). Subsequent requests are fast.
- **State is ephemeral**: SQLite and the demo calendar live in `/tmp` per warm instance. The
  account's Lambda concurrency quota is 10, so concurrency cannot be pinned to 1; a preview and its
  confirm landing on different instances is rejected with 409 `plan_changed` rather than misapplied.
- The API key is a Lambda environment variable (visible to account admins), not Secrets Manager.
- Uploads capped at 4 MB (Vercel body limit). Never upload real school documents to this demo.
- Google/Microsoft sync is not implemented; only file export and the in-memory demo calendar.
