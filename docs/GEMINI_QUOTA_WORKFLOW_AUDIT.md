GEMINI_WORKFLOW_USERS=

```json
{
  "scope_commit": "09c6871116924ce164a1e93e2c337d8dabe6b636 (local tracked workflow/source snapshot; not proof of main runtime config)",
  "workflows": [
    {
      "workflow": "Approved Source Clip Preparation",
      "file": ".github/workflows/approved-source-clip-preparation.yml",
      "schedule_UTC": [],
      "model": [
        "UNKNOWN at runtime; inherited defaults/overrides, see model_defaults below"
      ],
      "operation": "media caption generation; Hybrid classify/generate/review",
      "category": "Production (conditional/manual or scheduled)",
      "scheduled_start_in_window_static": "NO schedule"
    },
    {
      "workflow": "Autonomous Growth Loop Liver Manager",
      "file": ".github/workflows/autonomous-growth-loop-liver-manager.yml",
      "schedule_UTC": [
        "45 0 * * *",
        "45 3 * * *",
        "45 11 * * *"
      ],
      "model": [
        "UNKNOWN at runtime; inherited defaults/overrides, see model_defaults below"
      ],
      "operation": "scheduled text generation; Hybrid classify/generate/review",
      "category": "Production (conditional/manual or scheduled)",
      "scheduled_start_in_window_static": "NO cron start in window; earlier/delayed execution UNKNOWN"
    },
    {
      "workflow": "Autonomous Growth Loop Night Scout",
      "file": ".github/workflows/autonomous-growth-loop-night-scout.yml",
      "schedule_UTC": [
        "45 4 * * *",
        "45 6 * * *",
        "45 15 * * *"
      ],
      "model": [
        "UNKNOWN at runtime; inherited defaults/overrides, see model_defaults below"
      ],
      "operation": "scheduled text generation; Hybrid classify/generate/review",
      "category": "Production (conditional/manual or scheduled)",
      "scheduled_start_in_window_static": "NO cron start in window; earlier/delayed execution UNKNOWN"
    },
    {
      "workflow": "Autopilot AUTO_READY Pilot",
      "file": ".github/workflows/autopilot-auto-ready.yml",
      "schedule_UTC": [
        "7 */2 * * *"
      ],
      "model": [
        "UNKNOWN at runtime; inherited defaults/overrides, see model_defaults below"
      ],
      "operation": "maintain_text_ready_inventory; buffered_original_generation; Hybrid gate",
      "category": "Production (conditional/manual or scheduled)",
      "scheduled_start_in_window_static": "YES: 06:07 UTC"
    },
    {
      "workflow": "Beauty Threads Production",
      "file": ".github/workflows/beauty-threads-production.yml",
      "schedule_UTC": [
        "30 0 * * *",
        "30 9 * * *",
        "30 2 * * *",
        "30 11 * * *"
      ],
      "model": [
        "GEMINI_MODEL: ${{ vars.BEAUTY_GEMINI_MODEL || 'gemini-2.5-flash-lite' }}"
      ],
      "operation": "Beauty text generation; Hybrid gate; conditional publish",
      "category": "Production (conditional/manual or scheduled)",
      "scheduled_start_in_window_static": "NO cron start in window; earlier/delayed execution UNKNOWN"
    },
    {
      "workflow": "CI Security and Regression",
      "file": ".github/workflows/ci.yml",
      "schedule_UTC": [],
      "model": [
        "UNKNOWN at runtime; inherited defaults/overrides, see model_defaults below"
      ],
      "operation": "mock/regression tests; external API probes excluded",
      "category": "CI",
      "scheduled_start_in_window_static": "NO schedule"
    },
    {
      "workflow": "Content Pilot Publish",
      "file": ".github/workflows/content-pilot-publish.yml",
      "schedule_UTC": [],
      "model": [
        "UNKNOWN at runtime; inherited defaults/overrides, see model_defaults below"
      ],
      "operation": "credential preflight / PDCA; actual Gemini request UNKNOWN",
      "category": "Production (conditional/manual or scheduled)",
      "scheduled_start_in_window_static": "NO schedule"
    },
    {
      "workflow": "Deploy Buffered Production Runtime",
      "file": ".github/workflows/deploy-buffered-production-runtime.yml",
      "schedule_UTC": [],
      "model": [
        "UNKNOWN at runtime; inherited defaults/overrides, see model_defaults below"
      ],
      "operation": "exports Gemini credential to hosted runtime; runtime generation conditional",
      "category": "Production (conditional/manual or scheduled)",
      "scheduled_start_in_window_static": "NO schedule"
    },
    {
      "workflow": "Direct Media Preparation",
      "file": ".github/workflows/direct-media-preparation.yml",
      "schedule_UTC": [
        "45 1 * * *"
      ],
      "model": [
        "GEMINI_CLASSIFIER_MODEL: ${{ vars.GEMINI_CLASSIFIER_MODEL || 'gemini-3.1-flash-lite' }}",
        "GEMINI_GENERATOR_MODEL: ${{ vars.GEMINI_GENERATOR_MODEL || 'gemini-3.5-flash' }}",
        "GEMINI_GENERATOR_MODEL: gemini-3.5-flash",
        "GEMINI_REVIEW_MODEL: ${{ vars.GEMINI_REVIEW_MODEL || 'gemini-3.1-flash-lite' }}",
        "GEMINI_VISION_MODEL: gemini-3.5-flash"
      ],
      "operation": "Smoke media_visual_understanding -> vision_smoke_relevance -> direct_reference_caption_generation; Production media preparation/Hybrid gate",
      "category": "Production / Smoke",
      "scheduled_start_in_window_static": "NO cron start in window; earlier/delayed execution UNKNOWN"
    },
    {
      "workflow": "Direct Reference Media Liver Manager",
      "file": ".github/workflows/direct-reference-media-liver-manager.yml",
      "schedule_UTC": [
        "45 6 * * *"
      ],
      "model": [
        "UNKNOWN at runtime; inherited defaults/overrides, see model_defaults below"
      ],
      "operation": "saved caption normalization; Hybrid classify/generate/review",
      "category": "Production (conditional/manual or scheduled)",
      "scheduled_start_in_window_static": "NO cron start in window; earlier/delayed execution UNKNOWN"
    },
    {
      "workflow": "Direct Reference Media Night Scout",
      "file": ".github/workflows/direct-reference-media-night-scout.yml",
      "schedule_UTC": [
        "45 8 * * *"
      ],
      "model": [
        "UNKNOWN at runtime; inherited defaults/overrides, see model_defaults below"
      ],
      "operation": "saved caption normalization; Hybrid classify/generate/review",
      "category": "Production (conditional/manual or scheduled)",
      "scheduled_start_in_window_static": "NO cron start in window; earlier/delayed execution UNKNOWN"
    },
    {
      "workflow": "Hybrid AI Gate - Liver Manager",
      "file": ".github/workflows/hybrid-ai-gate-liver-manager.yml",
      "schedule_UTC": [],
      "model": [
        "GEMINI_CLASSIFIER_MODEL: ${{ vars.GEMINI_CLASSIFIER_MODEL || 'gemini-3.1-flash-lite' }}",
        "GEMINI_GENERATOR_MODEL: ${{ vars.GEMINI_GENERATOR_MODEL || 'gemini-3.5-flash' }}",
        "GEMINI_REVIEW_MODEL: ${{ vars.GEMINI_REVIEW_MODEL || 'gemini-3.1-flash-lite' }}"
      ],
      "operation": "classify/generate/review",
      "category": "Production (conditional/manual or scheduled)",
      "scheduled_start_in_window_static": "NO schedule"
    },
    {
      "workflow": "Hybrid AI Gate - Night Scout",
      "file": ".github/workflows/hybrid-ai-gate-night-scout.yml",
      "schedule_UTC": [],
      "model": [
        "GEMINI_CLASSIFIER_MODEL: ${{ vars.GEMINI_CLASSIFIER_MODEL || 'gemini-3.1-flash-lite' }}",
        "GEMINI_GENERATOR_MODEL: ${{ vars.GEMINI_GENERATOR_MODEL || 'gemini-3.5-flash' }}",
        "GEMINI_REVIEW_MODEL: ${{ vars.GEMINI_REVIEW_MODEL || 'gemini-3.1-flash-lite' }}"
      ],
      "operation": "classify/generate/review",
      "category": "Production (conditional/manual or scheduled)",
      "scheduled_start_in_window_static": "NO schedule"
    },
    {
      "workflow": "Media Approved Pilot",
      "file": ".github/workflows/media-approved-pilot.yml",
      "schedule_UTC": [],
      "model": [
        "UNKNOWN at runtime; inherited defaults/overrides, see model_defaults below"
      ],
      "operation": "credential presence in preflight; actual Gemini request UNKNOWN",
      "category": "Production (conditional/manual or scheduled)",
      "scheduled_start_in_window_static": "NO schedule"
    },
    {
      "workflow": "Media Growth Post Liver Manager",
      "file": ".github/workflows/media-growth-post-liver-manager.yml",
      "schedule_UTC": [
        "45 8 * * *"
      ],
      "model": [
        "UNKNOWN at runtime; inherited defaults/overrides, see model_defaults below"
      ],
      "operation": "media caption generation; Hybrid classify/generate/review",
      "category": "Production (conditional/manual or scheduled)",
      "scheduled_start_in_window_static": "NO cron start in window; earlier/delayed execution UNKNOWN"
    },
    {
      "workflow": "Media Growth Post Night Scout",
      "file": ".github/workflows/media-growth-post-night-scout.yml",
      "schedule_UTC": [
        "45 11 * * *"
      ],
      "model": [
        "UNKNOWN at runtime; inherited defaults/overrides, see model_defaults below"
      ],
      "operation": "media caption generation; Hybrid classify/generate/review",
      "category": "Production (conditional/manual or scheduled)",
      "scheduled_start_in_window_static": "NO cron start in window; earlier/delayed execution UNKNOWN"
    },
    {
      "workflow": "Source Fetch Dry-Run",
      "file": ".github/workflows/source-fetch-dry-run.yml",
      "schedule_UTC": [],
      "model": [
        "UNKNOWN at runtime; inherited defaults/overrides, see model_defaults below"
      ],
      "operation": "credential preflight; actual Gemini request UNKNOWN",
      "category": "Smoke (manual dry-run)",
      "scheduled_start_in_window_static": "NO schedule"
    },
    {
      "workflow": "Threads Video Reference Preparation",
      "file": ".github/workflows/threads-video-reference-preparation.yml",
      "schedule_UTC": [],
      "model": [
        "UNKNOWN at runtime; inherited defaults/overrides, see model_defaults below"
      ],
      "operation": "reference caption generation",
      "category": "Production (conditional/manual or scheduled)",
      "scheduled_start_in_window_static": "NO schedule"
    },
    {
      "workflow": "TikTok Shop Threads Onboarding",
      "file": ".github/workflows/tiktok-shop-threads-onboarding.yml",
      "schedule_UTC": [],
      "model": [
        "UNKNOWN at runtime; inherited defaults/overrides, see model_defaults below"
      ],
      "operation": "managed account candidate generation; Hybrid classify/generate/review",
      "category": "Production (conditional/manual or scheduled)",
      "scheduled_start_in_window_static": "NO schedule"
    },
    {
      "workflow": "Video Reference Dry-Run",
      "file": ".github/workflows/video-reference-dry-run.yml",
      "schedule_UTC": [],
      "model": [
        "UNKNOWN at runtime; inherited defaults/overrides, see model_defaults below"
      ],
      "operation": "reference caption generation (conditional)",
      "category": "Smoke (manual dry-run)",
      "scheduled_start_in_window_static": "NO schedule"
    },
    {
      "workflow": "CI WP3 Production Read-Only Verification",
      "file": ".github/workflows/wp3-production-readonly-verification.yml",
      "schedule_UTC": [],
      "model": [
        "UNKNOWN at runtime; inherited defaults/overrides, see model_defaults below"
      ],
      "operation": "credential presence audit/preview; no confirmed Gemini generation",
      "category": "CI",
      "scheduled_start_in_window_static": "NO schedule"
    }
  ],
  "scripts_and_modules_direct_references": [
    "scripts/activated_autopost_test_utils.py",
    "scripts/apply_v29_voice_correction.py",
    "scripts/check_credentials_readiness.py",
    "scripts/evidence_context_caption.py",
    "scripts/gemini_hybrid_client.py",
    "scripts/generate_from_jobs.py",
    "scripts/generate_threads_ideas_from_references.py",
    "scripts/maintain_text_ready_inventory.py",
    "scripts/preflight_check.py",
    "scripts/preflight_real_llm_generation.py",
    "scripts/prepare_beauty_review_candidates.py",
    "scripts/print_env_status.py",
    "scripts/run_buffered_media_preparation_host.py",
    "scripts/run_content_quality_v2_vision_smoke.py",
    "scripts/run_hybrid_ai_queue_gate.py",
    "scripts/run_scheduled_autopost_preview_v2.py",
    "scripts/run_scheduled_autopost_readonly_audit.py",
    "scripts/scheduled_execution_guard.py",
    "scripts/test_beauty_generation_novelty.py",
    "scripts/test_beauty_voice_corpus_style_and_isolation.py",
    "scripts/test_buffered_generation.py",
    "scripts/test_buffered_host_runtime_contract.py",
    "scripts/test_buffered_media_preparation_host.py",
    "scripts/test_content_quality_v2_vision_smoke.py",
    "scripts/test_direct_content_understanding_contract.py",
    "scripts/test_end_to_end_autopost_contract.py",
    "scripts/test_gemini_hybrid_client.py",
    "scripts/test_gemini_real.py",
    "scripts/test_gemini_vision_provider.py",
    "scripts/test_media_preparation_failure_classification.py",
    "scripts/test_offline_original_ready_reserve.py",
    "scripts/test_production_inventory.py",
    "scripts/test_ready_inventory_maintenance_contract.py",
    "scripts/test_scheduled_runtime_blockers.py",
    "src/config_loader.py",
    "src/generation/reference_source_rewriter.py",
    "src/llm_client.py",
    "src/media/gemini_vision.py",
    "tests/test_beauty_production_workflows.py",
    "tests/test_llm_client_json_mime.py",
    "tests/test_reference_rehearsal_robustness.py"
  ],
  "model_defaults": {
    "hybrid_classifier_review": "gemini-3.1-flash-lite",
    "hybrid_generator": "gemini-3.5-flash",
    "vision_smoke": "gemini-3.5-flash",
    "llm_client": "gemini-2.5-flash",
    "reference_source_rewriter": "gemini-3.6-flash; existing fallback gemini-2.5-flash-lite",
    "evidence_context_caption": "gemini-3.5-flash; existing fallback gemini-3.1-flash-lite"
  },
  "limitations": "Direct key/client/API references plus repository-test workflow. Credential presence does not prove a request. Runtime overrides, dynamic imports, external hosts, and shared-project workloads are UNKNOWN. No secrets inspected."
}
```

POSSIBLE_SCHEDULE_OVERLAP=

```json
{
  "result": "UNKNOWN",
  "window_UTC": [
    "2026-10-02T05:50:06Z",
    "2026-10-02T06:20:06Z"
  ],
  "static_candidate": "Autopilot AUTO_READY Pilot: 7 */2 * * *, nominal 06:07 UTC; actual Gemini calls UNKNOWN",
  "scheduled_runs_created_in_window": [
    {
      "id": 36971242764,
      "workflow": "Beauty Threads Production",
      "created_at": "2026-10-02T05:57:05Z",
      "conclusion": "skipped"
    },
    {
      "id": 36972618735,
      "workflow": "Autonomous Growth Loop Liver Manager",
      "created_at": "2026-10-02T06:14:39Z",
      "conclusion": "skipped"
    }
  ],
  "api_query_total_count": 2,
  "observed_run_head": "4aa37f5c6409e0d9faa6d1e3e90d248f1984ced3",
  "limitation": "The two returned scheduled runs were skipped. This does not establish quota causality or exclude earlier long-running work, other projects/repos, or external hosted schedules. Local feature schedule differs from actual default-branch runtime snapshot."
}
```
