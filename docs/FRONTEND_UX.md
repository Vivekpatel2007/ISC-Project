# Frontend UX and Appearance Review

## Run the application

From the project root, after the [local setup](LOCAL_SETUP.md):

```powershell
npm.cmd run dev
```

Open `http://localhost:3000/login/staff` or `http://localhost:3000/login/radiologist`. Enter the corresponding demo credentials manually. This UI refresh uses the existing backend endpoints and account permissions.

## Appearance

- The sun/moon button is available on both login pages and in the workspace header.
- Light and dark themes cover every screen, form, table, notice, and screening result.
- A first visit follows the device's color preference. An explicit toggle choice is remembered across visits.
- Profile & preferences offers Light, Dark, and System. System follows subsequent device theme changes.
- Only the appearance preference (`pulmoscan.theme`) and login portal preference are stored. Authentication tokens and credentials remain in memory.
- Appearance changes also synchronize across tabs on the same origin. Keep using the same host (`localhost` or `127.0.0.1`) for browser preferences to be shared.

## Workspaces and navigation

- Clinical staff see their own scan overview, a primary upload action, and My scans.
- Radiologists and administrators see the institutional overview and a shortcut to the pending screening queue.
- Metrics are calculated from records returned by the backend. No demo counts or artificial activity trends are added to the application.
- The active sidebar link remains highlighted on a scan detail page.
- On smaller screens, the menu opens as a modal drawer. Escape closes it, focus stays within the modal, and selecting a link closes the drawer.
- A skip-to-content link and visible keyboard focus indicators support keyboard navigation. Motion is reduced when the device requests reduced motion.

## Scan repository

- Search by patient identifier, scan identifier, or uploader.
- Filter All scans, Pending, and Screened; clear active filters in one action.
- Sort by newest, oldest, or patient identifier.
- Browse eight records per page. Search and filter changes return to the first page.
- Desktop uses a table; mobile uses readable scan cards.
- A failed request shows a retry action instead of claiming the repository is empty. A failed refresh can retain previously loaded records while showing the error.

## Upload and screening

- Upload accepts a single PNG or JPEG up to 20 MB, with a local preview and a removable selection.
- The patient reference is validated before upload. No patient names or personal details are requested.
- Duplicate upload and screening submissions are blocked while a request is running.
- After saving, the preview URL is revoked and a confirmation links to the new scan. Screening runs only when the practitioner chooses to run it.
- Results distinguish the model's class confidence from its normal and pneumonia probabilities. The decision threshold and clinical review notice remain visible.
- If screening succeeds but the metadata refresh fails, the successful result stays visible with a status-refresh warning.
- If a screening rerun reports an integrity error, the previous probability result is removed to avoid presenting it as the latest output.

## Manual review checklist

1. On each login portal, switch light/dark mode, refresh, and reopen the page. Confirm the portal and theme are retained and credentials remain empty.
2. Sign in as staff. Check the overview, upload action, My scans, and Profile & preferences.
3. Sign in as a radiologist. Open the screening queue and confirm Pending is selected.
4. In the repository, combine search, a status filter, and sorting. Check pagination with more than eight records and clear the filters.
5. Upload an invalid file, then a valid radiograph and patient identifier. Confirm the saved scan link opens its details.
6. Run screening. Review both probability bars, the confidence label, and clinical review notice.
7. At a mobile viewport, use the navigation drawer with the keyboard and Escape. Check that pages fit without horizontal page scrolling.
8. In Profile & preferences, select System, then change the device theme. Sign out and confirm the login portal remains correct with blank fields.

## Automated validation

```powershell
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run build
```

Theme tests cover device defaults, stored choices, storage restrictions, cross-tab updates, and system changes. Existing authentication and authorization UI tests remain in place. Repository, upload, and screening tests cover the corresponding data and error flows.
