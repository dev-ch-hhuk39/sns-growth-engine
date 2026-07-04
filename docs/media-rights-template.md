# Media Rights Template

Use this template before any owned, licensed, or approved creator material enters the media pipeline.

Third-party reference material with `third_party_reference_only` or `unknown` rights is not media pipeline eligible. It may be used for reference analysis only and must not be saved, downloaded, cut, uploaded, reposted, or lightly rewritten into a post.

## Required Fields

| field | required content |
|---|---|
| `asset_id` | Stable asset identifier. |
| `platform` | `local`, `youtube`, `tiktok`, `threads`, `x`, or another reviewed source. |
| `source_url` | Original source URL, if any. Leave empty only when `local_file_ref` is sufficient. |
| `local_file_ref` | Local file reference or storage pointer. Do not commit the actual file under `data/` or `output/`. |
| `owner_name` | Legal owner or brand/company that controls the material. |
| `creator_name` | Creator/performer/editor name if different from owner. |
| `permission_source` | Contract, invoice, release form, email, DM, internal production record, or other evidence source. |
| `permission_evidence_url_or_file` | Evidence pointer. Do not paste secrets or private tokens. |
| `permission_status` | `approved`, `pending`, `expired`, or `rejected`. Media pipeline requires `approved`. |
| `permission_scope` | Explicit allowed actions such as `download`, `transcribe`, `analyze`, `cut`, `subtitle`, `upload`, `repost_to_threads`, `use_for_post_text`, `pdca_analysis`. |
| `permission_evidence_type` | Evidence class such as `contract`, `email`, `dm`, `release_form`, `internal_record`, or `user_asserted_permission`. |
| `permission_evidence_note` | Short note explaining the permission basis without secrets or private token values. |
| `permission_approved_by` | Human/operator who approved the permission record. |
| `permission_approved_at` | Approval timestamp/date. |
| `permission_date` | Date permission was granted. |
| `permission_expire_date` | Expiration date, or `none` only when permission is perpetual and documented. |
| `rights_status` | `owned`, `licensed`, or `approved_creator_clip`. |
| `allowed_platforms_for_repost` | Repost platforms explicitly allowed, for example `["threads"]`. |
| `allowed_uses` | `save`, `cut`, `upload`, `repost`, `derivative_post`, `paid_ad`, `organic_post`. |
| `prohibited_uses` | Any excluded use, platform, region, ad use, or duration. |
| `target_account_id` | `night_scout`, `liver_manager`, or another reviewed account. |
| `notes` | Scope, context, and review notes. |
| `reviewed_by` | Human reviewer. |
| `reviewed_at` | Review timestamp/date. |

## JSON Skeleton

```json
{
  "asset_id": "",
  "platform": "local",
  "source_url": "",
  "local_file_ref": "",
  "owner_name": "",
  "creator_name": "",
  "permission_source": "",
  "permission_evidence_url_or_file": "",
  "permission_status": "approved",
  "permission_scope": [
    "download",
    "transcribe",
    "analyze",
    "cut",
    "subtitle",
    "upload",
    "repost_to_threads",
    "use_for_post_text",
    "pdca_analysis"
  ],
  "permission_evidence_type": "",
  "permission_evidence_note": "",
  "permission_approved_by": "",
  "permission_approved_at": "",
  "permission_date": "",
  "permission_expire_date": "",
  "rights_status": "owned",
  "allowed_platforms_for_repost": ["threads"],
  "allowed_uses": {
    "save": false,
    "cut": false,
    "upload": false,
    "repost": false,
    "derivative_post": true,
    "paid_ad": false,
    "organic_post": true
  },
  "prohibited_uses": "",
  "target_account_id": "",
  "notes": "",
  "reviewed_by": "",
  "reviewed_at": ""
}
```

## Review Rules

- A DM permission is not enough by itself unless the evidence pointer, permitted platforms, duration, and allowed uses are recorded.
- If a campaign or licensing deal permits secondary use, record the expiration date, media/platform scope, ad/organic scope, and any excluded edits.
- `unknown` remains blocked until human review changes the rights status to `owned`, `licensed`, or `approved_creator_clip`.
- `third_party_reference_only` remains analysis-only forever unless a separate permission record is created.
- Real cut/upload still requires the existing command gates such as `ALLOW_VIDEO_CUT=true` plus `--confirm-cut`, or `ALLOW_CLOUDINARY_UPLOAD=true` plus `--confirm-upload`.
