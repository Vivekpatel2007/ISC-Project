# PulmoScan frontend

The practitioner interface for secure chest X-ray screening. FastAPI performs authentication, access checks, encryption, storage, classification and Grad-CAM computation. See the [root README](../README.md) for the complete project and setup.

## Pages and workflow

| Page | Purpose |
| --- | --- |
| `/login/staff`, `/login/radiologist` | Practitioner portals; `/login` restores the portal preference |
| `/` | Overview of accessible records and activity |
| `/upload` | PNG/JPEG upload and preview using a pseudonymous patient ID |
| `/patients` | Latest-upload status, patient grouping and scan history |
| `/scans`, `/scans/[id]` | Repository, screening, image inspection and optional explanations |
| `/profile` | Own-account edit dialogs, appearance and active model identity |

Staff use the backend role `doctor`; admin accounts also use the staff portal. Staff can access their own uploads; radiologists/admins can access all scans. Patients have no login accounts. Backend authorization applies regardless of the UI.

Features include light/dark themes, enlarged X-rays and zoom, patient follow-ups, ID correction/deletion and practitioner name/username/password editing. A newer pending upload does not inherit an older scan's result.

## Model output and explanations

Class scores are **uncalibrated**. The UI displays saturated/rounded scores as `>99.99%` rather than certainty. The loaded checkpoint determines preprocessing and cutoff; the default DenseNet121 uses 0.40, while another candidate can use a different saved cutoff. Compute labels come from the actual backend device, not a fixed GPU name.

**Explain prediction** requests a class/model-bound Grad-CAM map after fresh screening. Numbered sections link to spatial notes; Original/Heatmap switching, opacity and zoom operate on the same image. Text describes model contributions, not clinical findings or confirmed pneumonia locations. See [explainability](../docs/EXPLAINABILITY.md).

## Session and image handling

- The app does not persist tokens/passwords in localStorage, sessionStorage or cookies. Portal and appearance preferences may persist.
- Refreshing or closing the tab ends the in-memory session. Reported expiry and matching protected-request 401 responses clear it too; old-token responses cannot sign out a replacement session.
- Protected image requests use temporary blob URLs that are revoked during cleanup. API fetches request no browser caching.
- Uploading stores an encrypted copy and leaves the selected source file unchanged. Multipart ingestion can spool before encryption, so this is not a guarantee of zero plaintext disk use.

## Setup and manual startup

Use Python **3.11**, Node.js **22.13+ within 22.x, 24.x, or 26+**, and npm **10+**. Complete the [Windows or Linux root setup](../README.md#local-setup-and-running-the-application) first, including the project environment, compute/shared Python dependencies, both npm lockfiles and local configuration.

After that setup, from the project root:

```bash
npm run dev:check
npm run dev
```

Use `npm.cmd` instead of `npm` in Windows PowerShell if its script shim is blocked. Ctrl+C stops both services. For frontend only, run `npm run dev:frontend` after preflight, with a separately started backend. Dependencies are not reinstalled on each launch.

`frontend/.env.local` normally points `NEXT_PUBLIC_API_BASE_URL` to `http://127.0.0.1:8000`; this is public configuration, not a place for secrets. The root environment helper creates missing configuration and preserves existing keys/files. The source and saved checkpoint are required, but a training dataset is not.

Demo credentials in the root README are for local use only and are seeded only into an empty users table when enabled. Local HTTP is not a remote HTTPS deployment.

## Stack and verification

Next.js 16.4.3, React 19.3.0, TypeScript, Tailwind CSS, Lucide icons, Vitest and React Testing Library. Vitest uses `vitest.config.mts`.

From the project root:

```bash
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run build
```

On Windows PowerShell, use `npm.cmd` for these commands.

The baseline application review on **13 November 2026** passed **106 frontend tests**, lint and production build; the backend passed **232 tests**. These are functional checks, not medical validation. See [the final review](../docs/FINAL_REVIEW_2026-11-13.md) and [manual handoff](../docs/PROJECT_HANDOFF.md). Test/build commands do not start application servers.

See [16 November finalization](../docs/FINALIZATION_2026-11-16.md) for the latest check and generalized setup requirements.
