# Model artifact registry

The registry is governance machinery, not approval of the current CCHIS model. The current local state is:

```json
{
  "active_model_count": 0,
  "operational_model_available": false,
  "readiness": "NOT_APPROVED_FOR_OPERATIONAL_USE"
}
```

No model is approved, active, retired, rolled back, or represented as operational by this correction pass.

## Contract

`ModelRun` remains the source of training, inference, feature-dataset, evaluation and Phase 4 evidence. `ModelRegistryEntry` adds the stable registry version, artifact reference and integrity facts, ordered feature contract, code commit, truth classification, intended/prohibited use and independent approval/lifecycle state. `ModelGovernanceEvent` records each state transition. New events require an active CCHIS user, preserve the actor snapshot and previous/resulting states, and reject model/queryset updates and deletes; the strict audit also validates the complete event sequence.

Artifacts are never deserialized during registration or audit. The controlled storage root is `MODEL_ARTIFACT_ROOT` (Compose default `/var/lib/cchis/model_artifacts`). The supported local storage schemes are `file` and `local`; supported formats are `joblib`, `pickle` and `onnx`. Registration persists SHA-256 and byte size, and approval/activation re-hashes the file. Missing, moved, modified, unsupported or out-of-root artifacts fail closed.

Approval requires a successful model run, real live training/inference and label dataset references, non-empty evaluation metrics, truth-policy evidence, matching ordered feature contracts and an intact artifact. The persisted truth evaluator runs for candidates being approved, activated or selected as rollback targets regardless of `CCHIS_ENVIRONMENT`; registration remains candidate-permissive. Activation additionally requires Phase 4 promotion evidence and the operational `live_baseline` target. Challengers remain non-operational. At most one active entry may exist per deployment target. Rollback requires an explicitly named compatible target; the registry never infers a prior database row.

The governed commands resolve `--actor`/`--rolled-back-by` to an existing active CCHIS user and enforce the required role. A caller-supplied role string is not accepted as authorization, and the approval reviewer cannot be the user who requested that review. The local database contains no registered, approved or active model as of this correction pass.

## Governed commands

All mutation commands require a non-empty actor and reason. Outputs contain identifiers, state and integrity metadata only.

```bash
docker compose exec -T backend python manage.py register_model_artifact \
  --model-run-id <successful-run-id> \
  --artifact-path /var/lib/cchis/model_artifacts/<artifact-file> \
  --actor <active-cchis-user-id-or-username> --reason "Candidate registration"

docker compose exec -T backend python manage.py request_model_approval \
  --registry-ref <registry-id-or-version> \
  --actor <active-cchis-user-id-or-username> --reason "Request independent review"

docker compose exec -T backend python manage.py approve_model_artifact \
  --registry-ref <registry-id-or-version> \
  --actor <active-admin-user-id-or-username> --reason "Evidence reviewed"

docker compose exec -T backend python manage.py designate_model_challenger \
  --registry-ref <registry-id-or-version> \
  --actor <active-cchis-user-id-or-username> --reason "Benchmark challenger"

docker compose exec -T backend python manage.py activate_registered_model \
  --registry-ref <registry-id-or-version> \
  --actor <active-admin-user-id-or-username> --reason "Approved operational activation"

docker compose exec -T backend python manage.py rollback_registered_model \
  --rollback-target <retired-registry-id-or-version> \
  --actor <active-admin-user-id-or-username> --reason "Restore approved target"
```

The commands above are a runbook, not evidence that they were run. Do not run approval or activation against the current local database until the real artifact, evidence review and operational decision exist.

## Read-only audit and evidence

Use the read-only audit to distinguish registry integrity from operational readiness:

```bash
docker compose exec -T backend python manage.py audit_model_registry --strict
```

A sanitized no-active result is represented as:

```json
{
  "schema_version": "model-artifact-registry-audit-v1",
  "overall_status": "pass",
  "summary": {
    "registered_entry_count": 0,
    "active_model_count": 0,
    "operational_model_available": false
  },
  "readiness": {
    "active_model_count": 0,
    "operational_model_available": false,
    "readiness": "NOT_APPROVED_FOR_OPERATIONAL_USE"
  }
}
```

Evidence packages may include registry version, model-run ID, dataset references, state, event type, actor identifier, metric names/values, artifact format, byte size and SHA-256. They must not include artifact contents, filesystem credentials, API keys, phone numbers, message bodies, raw provider payloads or unredacted environment values.

The production scoring gate resolves the approved active `live_baseline` entry and checks its artifact, run, target, ordered contract, source-backed datasets and strict truth evidence. The current training-on-demand pipeline has no trusted registered-artifact loader, so a valid entry receives the stable blocker `production_registered_inference_path_required` rather than being treated as operational. This is an explicit implementation gap, not evidence of production scoring readiness.

Focused verification:

```bash
docker compose exec -T backend python manage.py test risk.test_model_artifact_registry --verbosity 1
docker compose exec -T backend python manage.py test risk.test_truth_policy --verbosity 1
docker compose exec -T backend python manage.py makemigrations risk --check --dry-run
docker compose exec -T backend python manage.py migrate --check
docker compose exec -T backend python manage.py check
docker compose config --quiet
docker compose exec -T backend python manage.py audit_model_registry --strict
```

Correction-pass result: registry **22/22 passed**, strict truth-policy **22/22 passed**, migrations/checks/Compose validation passed, and the strict local audit passed with `registered_entry_count=0`, `event_count=0` (approval events zero), `active_model_count=0`, `operational_model_available=false`, and readiness `NOT_APPROVED_FOR_OPERATIONAL_USE`. No approval, activation or real local model registration was performed. The full repository suite is delegated to CI.
