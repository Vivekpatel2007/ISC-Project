# PulmoScan — Clinical Decision Support Frontend

Frontend user interface for the ISC engineering project:
**"AI-Based Pneumonia Detection from Chest X-Ray Images with Secure Storage and Transmission of Medical Data"**

PulmoScan provides a modern healthcare dashboard interface connecting clinicians and radiologists directly to the AES-256-GCM encrypted image repository and the retrained DenseNet121 deep learning model.

---

## 1. System Overview & Architecture

PulmoScan is engineered with **Next.js (App Router)**, **React 19**, **TypeScript**, and **Tailwind CSS**. It communicates with the FastAPI backend over authenticated REST endpoints:

```
[ Clinical Web Browser ]
        │  (Next.js App Router, React 19, TypeScript)
        │
        ├── In-Memory JWT Bearer Token (Zero Persistent Storage)
        │
        ▼  HTTP / REST (Port 8000)
[ FastAPI Backend ]
        │
        ├── RBAC Enforcement (Doctor vs Radiologist)
        │
        ├── AES-256-GCM Encrypted Storage (PX01 Container Format)
        │
        └── Retrained DenseNet121 AI Inference (PyTorch / CUDA)
```

---

## 2. Key Features

- **Strict In-Memory Session Security**: Access tokens and sensitive patient data are held exclusively in volatile React state. Plaintext tokens, passwords, and images are **never written** to `localStorage`, `sessionStorage`, or cookies. Refreshing the browser terminates the session immediately.
- **Role-Based Workflows**:
  - **Doctor**: Can securely upload radiographs with pseudonymous patient identifiers, review scans uploaded by their own account, and trigger DenseNet121 AI screening.
  - **Radiologist**: Diagnostic clearance across the entire institutional repository, capable of reviewing and running predictions on all patient scans.
- **Secure AES-256-GCM Radiograph Ingestion**:
  - Drag-and-drop file picker with instant client-side format (.png, .jpeg) and size (<=20MB) validation.
  - Revocable in-memory previews (`URL.revokeObjectURL`) to eliminate lingering image buffers.
- **DenseNet121 AI Screening Visualization**:
  - Displays calibrated class predictions (`NORMAL` or `PNEUMONIA`).
  - Accessible dual probability distribution bars (Pneumonia vs Normal).
  - Operating decision threshold indicator (`0.40`).
  - Hardware device indicator (`cuda` RTX 3050 or `cpu`).
  - Prominent mandatory educational prototype clinical disclaimer.
- **Data Integrity & Tampering Defense**:
  - If ciphertext bytes are altered on disk, the backend fails AES-GCM tag verification (409 Conflict) and the UI surfaces a prominent cryptographic tampering alert.

---

## 3. Technology Stack

- **Framework**: Next.js 16.4.3 (App Router with Turbopack)
- **UI Library**: React 19.3.0
- **Language**: TypeScript 5
- **Styling**: Tailwind CSS v4 with shared semantic color tokens for light and dark appearance, responsive tables/cards, and keyboard focus states.
- **Icons**: Lucide React
- **Testing**: Vitest, `@testing-library/react`, `@testing-library/jest-dom`, JSDOM

---

## 4. Pre-Seeded Demonstration Accounts

The backend database is pre-seeded with two practitioner accounts for evaluation:

| Role | Staff Username | Password | Full Name / Title | Permitted Scope |
|---|---|---|---|---|
| **Doctor** | `doctor1` | `DoctorPassword123!` | Dr. Sarah Chen, MD (Pediatrics) | Upload scans; view/predict own uploaded scans only. |
| **Radiologist** | `radiologist1` | `RadioPassword123!` | Dr. James Wilson, MD (Radiology) | View all institutional scans; run predictions across all scans. |

Enter credentials manually at `/login/staff` (doctor/admin) or `/login/radiologist`. The portal links switch pages without filling credentials. `/login` reopens the last selected portal; only this portal preference is remembered in localStorage. Account roles come from the backend profile, and an account must match the selected portal before a session is established.

---

## 5. Prerequisites

Use Python 3.11, Node.js 22+, and npm 10+ for the documented local setup. Complete the [setup guide](../docs/LOCAL_SETUP.md) first, including `.venv`, Python dependencies, and local configuration.

## 6. Installation & Setup

From the project root:

```powershell
npm.cmd ci
npm.cmd ci --prefix frontend
.\.venv\Scripts\python.exe scripts/setup_local_env.py
npm.cmd run dev:check
```

The setup helper creates missing environment files and preserves existing keys and settings. The frontend API URL defaults to `http://127.0.0.1:8000` in `frontend/.env.local`.

## 7. How to Run (PowerShell Commands)

From the project root, start both services manually in one terminal:

```powershell
npm.cmd run dev
```

Turborepo checks setup, then runs Next.js and FastAPI concurrently. Stop both with **Ctrl+C**. Open [Staff Login](http://localhost:3000/login/staff) or [Radiologist Login](http://localhost:3000/login/radiologist).

For separate terminals, run `npm.cmd run dev:frontend` and `npm.cmd run dev:backend` from the root. `npm.cmd run dev:plan` prints the task plan without starting either service.

---

## 8. Verification & Testing

### 8.1 Automated Frontend Tests (Vitest)
From `frontend/` directory:
```powershell
npm run test
```
**Coverage**: Automated unit and integration tests include:
- `api-client.test.ts`: JSON/FormData serialization, Bearer token headers, 401/409/network error extraction.
- `auth-context.test.tsx`: In-memory token management, login/logout transitions, route protection.
- `login-page.test.tsx`: Portal selection and persistence, credential clearing, role mismatch rejection, cancellation, and error alerts.
- `upload-page.test.tsx`: Format validation (JPEG/PNG), file size limits (20MB), patient ID regex validation.
- `scans-history.test.tsx`: Empty state, patient ID filtering, status button filters.
- `prediction-view.test.tsx`: Metadata rendering, DenseNet121 inference visualization, probability bars, GCM tampering detection.

### 8.2 Frontend Code Quality & Build Checks
```powershell
# ESLint check (0 warnings, 0 errors)
npm run lint

# TypeScript production build
npm run build
```

### 8.3 Backend Test Suite (Pytest)
From root project directory:
```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -v
```
**Results**: 33 backend tests passing (15 API RBAC tests + 18 Cryptography/Storage tests).

---

## 9. Security Principles & Limitations

1. **Zero Plaintext at Rest**: Decrypted images reside strictly in volatile memory during model evaluation and are never saved to disk or persistent browser caches.
2. **Authorization Boundary**: The frontend is treated as an untrusted client. The FastAPI backend enforces RBAC cryptographically via JWT claims on every single request.
3. **No Persistent Cookies**: Authentication is maintained in JavaScript memory. Closing the tab or refreshing the page clears the session by design.
4. **Educational Prototype Notice**:
   > **Disclaimer**: This application is built as an educational demonstration of AI-assisted decision support and cryptographic storage for an ISC project. It is not approved for autonomous diagnosis or clinical patient management without oversight from a certified physician or radiologist.
