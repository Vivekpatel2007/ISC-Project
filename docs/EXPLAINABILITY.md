# Optional Grad-CAM explanations

Implemented 11 November 2026. No model retraining, checkpoint promotion, extra dependencies, or monitoring services are required for this feature.

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
6. Expand **Explanation details** to inspect the target, feature layer, device/precision, and loaded-model SHA-256.

Re-running screening clears its previous explanation. Leaving the page aborts the browser request and disposes of its image preview; the synchronous backend computation may still finish after client disconnection. Explanation failure leaves the actual screening result visible and supports retry.

If the current model fingerprint or decision differs from the requested result, the API returns **409** and asks for fresh screening. An older backend without the required fingerprint/routes must be restarted manually with the updated code.

## What the map means

This implements [Grad-CAM](https://arxiv.org/abs/1610.02391) for the current DenseNet121 engine. It highlights spatial regions that contribute positively to the **selected class's raw logit**. It does not generate medical findings, lesion boundaries, anatomical diagnoses, or an assertion that a highlighted region contains pneumonia. It explains one class score, not the complete decision mechanism or saved thresholding rule.

Class logits are used rather than softmax probabilities because a saturated probability can have a vanishing gradient. The displayed prediction and its threshold remain unchanged. There is no language model generating a diagnostic narrative.

The map originates from `features.denseblock4` (normally a coarse 7×7 representation for 224×224 input). Smooth full-size rendering does not create high-resolution lesion evidence. A map with zero or effectively constant positive contribution returns `no_spatial_signal`; the UI explains this and shows no artificial highlight.

The dataset provides image-level class labels rather than annotated lesion outlines. These overlays therefore have **not** been validated as clinical localization or segmentation. Different maps also use their own relative intensity scale and cannot be compared as disease severity measurements.

Our eight offline checks included a normal-labelled benchmark image that Kaggle v2 classified as pneumonia with probability 1.0 on CPU and CUDA. The explanation faithfully accompanies that model output; it does not establish that the prediction is correct or that the label is wrong. The original checkpoint remains active by default.

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

The full suite passed **187 backend tests** and **92 frontend tests**, plus frontend lint and the Next.js production build. Verification includes:

- Analytically known feature locations and target-class specificity.
- A synthetic occlusion test that lowers the known target logit.
- Classifier-weight changes that change the map, and preservation of parameter values, existing gradients, frozen flags, evaluation modes, and RNG state.
- A real torchvision DenseNet check that reconstructed explanation logits equal its ordinary forward logits.
- Saturated softmax inputs with nonzero raw-logit Grad-CAM signal.
- Square, portrait, landscape, and extreme-aspect geometry, including padding removal and blank-map handling.
- Unauthorized/cross-doctor access, tampering, changed-model responses, no caching, and unchanged scan records.
- Opt-in generation, failed-request retry, identity matching, duplicate-request prevention, request cancellation, stale-map removal, opacity, and coupled zoom.

These analytical model-sensitivity and occlusion checks are inspired by [saliency-map sanity-check research](https://arxiv.org/abs/1810.03292). They are not a full parameter-randomization study, lesion-localization validation, or proof of clinical faithfulness.

Eight additional fixed-model offline checks used two actual dataset images with both the original and Kaggle v2 DenseNet on CPU and the local GTX 1650. Explanation probabilities agreed with normal prediction responses at their four-decimal API precision, overlays matched source dimensions, and all model state tensors remained unchanged. The separate real-DenseNet unit test also compares raw logits exactly on CPU. Observed explanation times in this small run ranged approximately **0.1–0.6 seconds**; these include in-process map generation/encoding, not HTTP/browser latency or a throughput benchmark.

Local evidence is ignored by Git under `data/review/gradcam_smoke_20261111/`: `report.json`, contribution PNGs, and illustrative overlays made from the public dataset samples. The production endpoint does not create these files. Before/after SHA-256 snapshots also verify that application storage, `.env`, and the active checkpoint were unchanged by testing. No development servers or training were started by the assistant.

An accurate portfolio statement after reviewing the feature is: **Implemented on-demand Grad-CAM with class/model provenance, protected image access, correct preprocessing alignment, CPU/CUDA execution, and automated explanation checks.** Avoid describing it as clinically validated localization or as improving classifier accuracy.
