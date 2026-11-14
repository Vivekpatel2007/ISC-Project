# Optional Grad-CAM explanations

Implemented 11 November 2026. No model retraining, checkpoint promotion, extra dependencies, or monitoring services are required for this feature.

**Scope decision, 13 November 2026:** retain Grad-CAM and its image-linked descriptions as the explanation feature for this prototype. Medical finding detection/report generation is deferred; no new dataset or Kaggle run is needed. See the [handoff and final review](PROJECT_HANDOFF.md).

## Review it manually

Start or restart the frontend/backend yourself from the project root:

```powershell
npm.cmd run dev
```

1. Sign in and open a scan. Upload a real, appropriately de-identified chest X-ray if needed.
2. Click **Run AI screening**. A fresh result with a loaded-model fingerprint is required by the UI; a saved historical label alone is insufficient.
3. Click **Explain prediction**. It runs only on request. Screening, follow-up, and patient record controls are disabled while explanation computation is in progress.
4. Use **View explanation on X-ray** to reach the image. The overlay appears automatically when a spatially informative map is available.
5. Switch between **Original** and **Heatmap**, adjust opacity, or click the image to use the enlarged viewer. The original image and overlay zoom together. The legend represents relative positive contribution, not probability or severity.
   - Numbered markers now link the image to **What contributed to this result?** below it. Select a note to emphasize its image section. The same notes and markers are available in the enlarged viewer.
6. Expand **Explanation details** to inspect the target, feature layer, device/precision, and loaded-model SHA-256.

Re-running screening clears its previous explanation. Leaving the page aborts the browser request and disposes of its image preview; the synchronous backend computation may still finish after client disconnection. Explanation failure leaves the actual screening result visible and supports retry.

If the current model fingerprint or decision differs from the requested result, the API returns **409** and asks for fresh screening. An older backend without the required fingerprint/routes must be restarted manually with the updated code.

## What the map means

This implements [Grad-CAM](https://arxiv.org/abs/1610.02391) for the current DenseNet121 engine. It highlights spatial regions that contribute positively to the **selected class's raw logit**. It does not generate medical findings, lesion boundaries, anatomical diagnoses, or an assertion that a highlighted region contains pneumonia. It explains one class score, not the complete decision mechanism or saved thresholding rule.

Class logits are used rather than softmax probabilities because a saturated probability can have a vanishing gradient. The displayed prediction and its threshold remain unchanged. There is no language model generating a diagnostic narrative.

The map originates from `features.denseblock4` (normally a coarse 7×7 representation for 224×224 input). Smooth full-size rendering does not create high-resolution lesion evidence. A map with zero or effectively constant positive contribution returns `no_spatial_signal`; the UI explains this and shows no artificial highlight.

The dataset provides image-level class labels rather than annotated lesion outlines. These overlays therefore have **not** been validated as clinical localization or segmentation. Different maps also use their own relative intensity scale and cannot be compared as disease severity measurements.

Our eight offline checks included a normal-labelled benchmark image that Kaggle v2 classified as pneumonia with probability 1.0 on CPU and CUDA. The explanation faithfully accompanies that model output; it does not establish that the prediction is correct or that the label is wrong. The original checkpoint remains active by default.

## Numbered image sections and plain-language text

The explanation now includes an image-specific spatial summary and numbered notes. For example, a real model check produced: **“For the PNEUMONIA output, stronger positive contributions appear in the middle-left, lower-left sections of the displayed image.”** Another normal-output image produced different locations and class-specific notes. These examples are model observations, not diagnoses or fixed text shown for every X-ray.

Each number identifies a strong contribution point inside a coarse image section. Selecting its note emphasizes that section with a dashed guide. Number labels remain inside their sections to avoid overlap; leader lines retain the actual contribution coordinates. The overlay uses the source image's SVG view box and the same aspect-preserving alignment as the image, including zoom.

The reading card now distinguishes the PNEUMONIA and NORMAL class scores without turning either into a clinical conclusion. Broad maps are labelled as broadly distributed contributions. A map with no useful spatial signal has no numbered notes or heatmap controls. **How to read this explanation** keeps color interpretation, coordinate limitations and original-image comparison guidance in a collapsed disclosure. The enlarged viewer's title/caption follows the actual Original/Heatmap mode; switching to Original also clears the visible selected-note state, and selecting a note restores its overlay.

Positions always mean **left/right/top/bottom of the displayed image**. The app does not infer patient laterality from JPEG/PNG pixels or assume verified DICOM orientation. Numbers count selected image sections, not lesions. A broad continuous highlight can span multiple numbered sections.

The text is generated deterministically from the actual, cropped contribution map:

1. Remove letterbox padding and normalize the visible contribution map, as for the heatmap.
2. Compare mean contribution in up to nine coarse displayed-image sections (a 3×3 grid where dimensions allow).
3. Describe at most three sections whose mean is at least 45% of the strongest section's mean. Mark an actual near-peak pixel in each selected section; points are not arbitrary section centers.
4. Report broad distribution when at least half the map has normalized intensity of 0.5 or greater. This is a rendering heuristic, not a medical threshold.
5. Produce no numbered regions when there is no spatially informative signal.

These heuristics summarize the Grad-CAM visualization. Their thresholds are not diagnostic cutoffs. The API supplies `summary`, `regions`, `distribution`, `coordinate_system="displayed_image"`, and `summary_basis="gradcam_spatial_v1"`; region bounds and marker coordinates are normalized to the source image. The frontend displays the notes only for this recognized method and coordinate system. Older responses without these fields still display their original heatmap; restart the backend and generate a fresh explanation to see the new text.

No external language model receives the images or writes clinical prose. The classifier was trained for NORMAL/PNEUMONIA, so the notes do not claim findings such as consolidation, pleural fluid, or anatomical abnormalities.

## If we later train for medical findings

This phase is **deferred**. A [dataset-access and detector plan, with a CPU-only annotation checker](FINDING_MODEL_NEXT_STEPS.md) is retained for the team; those are not current setup instructions. The existing Grad-CAM feature remains a contribution explanation; no finding detector has been trained or integrated.

The user has offered to run future training on Kaggle. That is not needed for the current numbered image/text feature, and no model architecture or weights were changed for it.

Reliable finding-level descriptions are a separate task. A future component would need suitable finding-level supervision or an appropriately validated pretrained medical model, plus finding-labelled evaluation data. Claims about finding locations need corresponding localization evidence or qualified review. A structured finding classifier with carefully grounded text is one possible path; image-report supervision is another. Re-training the existing two-class dataset alone does not provide those additional targets.

Before preparing that Kaggle workflow, define the supported findings, available labels, intended population, and independent evaluation. Keep the existing screening model and its contribution explanations separate from any new finding/report model until it is evaluated. This update does not add a finding detector, lung segmentation, or medical report generator.

## Implementation and safeguards

- `src/explainability.py` follows the DenseNet forward operations through its final normalization, non-in-place ReLU, global pooling, and classifier. It differentiates the target logit with respect to the last dense-block feature tensor.
- The prefix is evaluated without a training graph. Only the final feature tensor and head need gradients, reducing memory use. `torch.autograd.grad` avoids populating model parameter gradients. No optimizer, backward training step, hooks, model training-mode changes, or weight updates are used.
- The engine uses its existing prediction lock for explanation decoding, preprocessing, computation, and PNG encoding. These operations are serialized with predictions within a process.
- CPU uses float32. CUDA follows the same float16-autocast policy as prediction; spatial gradient averaging and heatmap math use float32. Different devices can produce different scores, so this feature does not claim bit-for-bit CPU/CUDA equivalence.
- Overlay geometry follows the checkpoint's preprocessing. Stretch maps are resized back to the source geometry; letterboxed maps remove the actual Pillow-sized padding before normalization and restoration. PNG dimensions match the decoded source image exactly.
- The original radiograph is not baked into the API overlay. The API returns an RGBA contribution image, class/model/image provenance, and a fixed interpretation statement. Browser controls blend it over the existing authorized preview.

The endpoint is **`POST /scans/{scan_id}/explain`**:

```json
{
  "target_class": "PNEUMONIA",
  "model_checkpoint_sha256": "<64-character lowercase SHA-256 from fresh prediction>"
}
```

Authentication, role/ownership checks, and the existing inference rate limiter apply. Authorization happens before image decryption or gradient computation. AES-GCM authentication and the stored image digest are verified. Responses use `Cache-Control: no-store, private`; credentials never appear in image URLs. Heatmaps are held in memory and are not inserted into SQLite or saved by the endpoint. Existing scan class, score, and status are not updated by explanation requests.

## Verification and limits

Final verification on 13 November 2026 passed **232 backend tests** and **106 frontend tests**, plus frontend lint, the Next.js production build and eight CPU/CUDA inference/explanation checks on the updated runtime. See [the final review](FINAL_REVIEW_2026-11-13.md) for exact scope, dependency checks and numerical comparisons, including the 14 November follow-up where the old metrics import block was not reproduced. Default pytest discovery targets `tests/`. Verification includes:

- Analytically known feature locations and target-class specificity.
- A synthetic occlusion test that lowers the known target logit.
- Classifier-weight changes that change the map, and preservation of parameter values, existing gradients, frozen flags, evaluation modes, and RNG state.
- A real torchvision DenseNet check that reconstructed explanation logits equal its ordinary forward logits.
- Saturated softmax inputs with nonzero raw-logit Grad-CAM signal.
- Square, portrait, landscape, and extreme-aspect geometry, including padding removal and blank-map handling.
- Unauthorized/cross-doctor access, tampering, changed-model responses, no caching, and unchanged scan records.
- Opt-in generation, failed-request retry, identity matching, duplicate-request prevention, request cancellation, stale-map removal, opacity, and coupled zoom.
- Image-specific numbered notes for both classes, changing hot-area positions, weak-section exclusion, broad/empty maps, thin geometry, and description coordinates after padding removal.
- Matched note/marker selection, original-image restoration, enlarged-view notes, and non-overlapping labels with leaders retaining actual contribution coordinates.
- Class-specific reading guidance, broad/missing-signal states, and enlarged-view mode labels and selected-note states that follow the visible overlay.

These analytical model-sensitivity and occlusion checks are inspired by [saliency-map sanity-check research](https://arxiv.org/abs/1810.03292). They are not a full parameter-randomization study, lesion-localization validation, or proof of clinical faithfulness.

Eight additional fixed-model offline checks used two actual dataset images with both the original and Kaggle v2 DenseNet on CPU and the local GTX 1650. Explanation probabilities agreed with normal prediction responses at their four-decimal API precision, overlays matched source dimensions, and all model state tensors remained unchanged. The separate real-DenseNet unit test also compares raw logits exactly on CPU. Observed explanation times in this small run ranged approximately **0.1–0.6 seconds**; these include in-process map generation/encoding, not HTTP/browser latency or a throughput benchmark.

Local evidence is ignored by Git under `data/review/gradcam_smoke_20261111/`: `report.json`, contribution PNGs, and illustrative overlays made from the public dataset samples. The production endpoint does not create these files. Before/after SHA-256 snapshots also verify that application storage, `.env`, and the active checkpoint were unchanged by testing. No development servers or training were started by the assistant.

The follow-up numbered-text checks are recorded in ignored `data/review/regions_smoke_20261111/report.json` with numbered overlay previews. Actual normal and pneumonia samples produced different class/location notes, with predictions identical before and after explanation. A second before/after fingerprint check confirmed no change to application storage, settings, or the active checkpoint. These are contribution-description checks, not validation of medical findings or localization.

An accurate portfolio statement after reviewing the feature is: **Implemented on-demand Grad-CAM with class/model provenance, protected image access, correct preprocessing alignment, CPU/CUDA execution, and automated explanation checks.** Avoid describing it as clinically validated localization or as improving classifier accuracy.
