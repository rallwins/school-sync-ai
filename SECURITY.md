# Security

- Uploads are untrusted: size cap, `%PDF-` magic check, full parse, page cap, encrypted PDFs rejected.
- No secrets in the repo. `.env` is git-ignored; `.env.example` has placeholders only.
- Sync to any real calendar always requires explicit user confirmation (not yet implemented).
- OAuth tokens will be stored server-side and encrypted, never in localStorage or logs (planned).
- Use synthetic PDFs for demos and bug reports. Do not attach real school documents to issues.

Report vulnerabilities privately to the repository owner rather than in a public issue.
Threat model: `docs/threat-model.md` (not yet written).
