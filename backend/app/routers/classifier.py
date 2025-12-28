"""Classifier endpoints for model status, debugging, and downloads."""

from fastapi import APIRouter, UploadFile, File
import structlog
from pathlib import Path

from app.services.classifier_service import get_classifier
from app.config import settings

router = APIRouter(prefix="/classifier", tags=["classifier"])
log = structlog.get_logger()

# Get shared classifier instance
classifier_service = get_classifier()


@router.get("/status")
async def classifier_status():
    """Return the status of the bird classifier model."""
    return classifier_service.get_status()


@router.get("/labels")
async def classifier_labels():
    """Return the list of species labels from the classifier model."""
    return {"labels": classifier_service.labels}


@router.get("/wildlife/status")
async def wildlife_classifier_status():
    """Return the status of the wildlife classifier model."""
    return classifier_service.get_wildlife_status()


@router.get("/wildlife/labels")
async def wildlife_classifier_labels():
    """Return the list of labels from the wildlife classifier model."""
    return {"labels": classifier_service.get_wildlife_labels()}


@router.get("/debug")
async def bird_classifier_debug():
    """Debug endpoint to inspect bird model details."""
    import numpy as np
    from PIL import Image

    try:
        bird = classifier_service._models.get("bird")

        if not bird or not bird.loaded:
            return {"error": "Bird model not loaded"}

        input_details = bird.input_details[0]
        output_details = bird.output_details[0]

        # Create a simple test image
        target_height, target_width = input_details['shape'][1], input_details['shape'][2]
        test_img = Image.new('RGB', (target_width, target_height), color=(100, 150, 200))

        # Prepare input based on model dtype
        if input_details['dtype'] == np.uint8:
            img_array = np.array(test_img, dtype=np.uint8)
        else:
            img_array = np.array(test_img, dtype=np.float32)
            img_array = (img_array - 127.0) / 128.0
        img_array = np.expand_dims(img_array, axis=0)

        # Run inference
        bird.interpreter.set_tensor(input_details['index'], img_array)
        bird.interpreter.invoke()
        raw_output = bird.interpreter.get_tensor(output_details['index'])

        # Get stats on raw output
        raw_squeezed = np.squeeze(raw_output).astype(np.float32)

        result = {
            "model_name": "bird",
            "input_dtype": str(input_details['dtype']),
            "input_shape": [int(x) for x in input_details['shape']],
            "output_dtype": str(output_details['dtype']),
            "output_shape": [int(x) for x in output_details['shape']],
            "raw_output_min": float(raw_squeezed.min()),
            "raw_output_max": float(raw_squeezed.max()),
            "raw_output_sum": float(raw_squeezed.sum()),
            "raw_output_mean": float(raw_squeezed.mean()),
            "top_5_raw_indices": [int(x) for x in raw_squeezed.argsort()[-5:][::-1]],
            "top_5_raw_values": [float(raw_squeezed[i]) for i in raw_squeezed.argsort()[-5:][::-1]],
            "labels_count": len(bird.labels),
        }

        # Check quantization params
        qp = output_details.get('quantization_parameters')
        if qp:
            result["quant_scales"] = [float(x) for x in qp.get('scales', [])] if qp.get('scales') is not None else None
            result["quant_zero_points"] = [int(x) for x in qp.get('zero_points', [])] if qp.get('zero_points') is not None else None

        # Also check legacy quantization tuple
        legacy_q = output_details.get('quantization')
        if legacy_q:
            result["legacy_quantization"] = str(legacy_q)

        # Dequantize if uint8
        if output_details['dtype'] == np.uint8:
            scales = qp.get('scales') if qp else None
            zero_points = qp.get('zero_points') if qp else None
            if scales is not None and len(scales) > 0:
                scale = scales[0]
                zero_point = zero_points[0] if zero_points is not None and len(zero_points) > 0 else 0
                dequant = (raw_squeezed - zero_point) * scale
                result["dequant_method"] = f"(x - {zero_point}) * {scale}"
            else:
                dequant = raw_squeezed / 255.0
                result["dequant_method"] = "x / 255.0"
            result["dequant_min"] = float(dequant.min())
            result["dequant_max"] = float(dequant.max())
            result["dequant_sum"] = float(dequant.sum())
            result["top_5_dequant_values"] = [float(dequant[i]) for i in raw_squeezed.argsort()[-5:][::-1]]

        return result
    except Exception as e:
        import traceback
        return {"error": str(e), "traceback": traceback.format_exc()}


@router.post("/test")
async def test_bird_classifier(image: UploadFile = File(...)):
    """Test bird classifier with an uploaded image."""
    from PIL import Image
    import io

    try:
        contents = await image.read()
        pil_image = Image.open(io.BytesIO(contents))

        results = classifier_service.classify(pil_image)

        return {
            "status": "ok",
            "image_size": pil_image.size,
            "image_mode": pil_image.mode,
            "results": results
        }
    except Exception as e:
        import traceback
        return {"error": str(e), "traceback": traceback.format_exc()}


@router.get("/wildlife/debug")
async def wildlife_classifier_debug():
    """Debug endpoint to inspect wildlife model details and test classification."""
    import numpy as np
    from PIL import Image

    try:
        wildlife = classifier_service._get_wildlife_model()

        if not wildlife or not wildlife.loaded:
            return {"error": "Wildlife model not loaded"}

        input_details = wildlife.input_details[0]
        output_details = wildlife.output_details[0]

        # Create a simple test image (solid red)
        test_img = Image.new('RGB', (224, 224), color=(255, 0, 0))
        img_array = np.array(test_img, dtype=np.uint8)
        img_array = np.expand_dims(img_array, axis=0)

        # Run inference
        wildlife.interpreter.set_tensor(input_details['index'], img_array)
        wildlife.interpreter.invoke()
        raw_output = wildlife.interpreter.get_tensor(output_details['index'])

        # Get stats on raw output
        raw_squeezed = np.squeeze(raw_output)

        result = {
            "input_dtype": str(input_details['dtype']),
            "input_shape": [int(x) for x in input_details['shape']],
            "output_dtype": str(output_details['dtype']),
            "output_shape": [int(x) for x in output_details['shape']],
            "raw_output_min": float(raw_squeezed.min()),
            "raw_output_max": float(raw_squeezed.max()),
            "raw_output_mean": float(raw_squeezed.mean()),
            "top_5_raw_indices": [int(x) for x in raw_squeezed.argsort()[-5:][::-1]],
            "top_5_raw_values": [float(raw_squeezed[i]) for i in raw_squeezed.argsort()[-5:][::-1]],
            "labels_count": len(wildlife.labels),
        }

        # Check quantization params
        qp = output_details.get('quantization_parameters')
        if qp:
            result["quant_scales"] = [float(x) for x in qp.get('scales', [])] if qp.get('scales') is not None else None
            result["quant_zero_points"] = [int(x) for x in qp.get('zero_points', [])] if qp.get('zero_points') is not None else None

        # Also check legacy quantization tuple
        legacy_q = output_details.get('quantization')
        if legacy_q:
            result["legacy_quantization"] = str(legacy_q)

        return result
    except Exception as e:
        import traceback
        return {"error": str(e), "traceback": traceback.format_exc()}


@router.post("/wildlife/test")
async def test_wildlife_classifier(image: UploadFile = File(...)):
    """Test wildlife classifier with an uploaded image."""
    from PIL import Image
    import io

    try:
        contents = await image.read()
        pil_image = Image.open(io.BytesIO(contents))

        results = classifier_service.classify_wildlife(pil_image)

        return {
            "status": "ok",
            "image_size": pil_image.size,
            "image_mode": pil_image.mode,
            "results": results
        }
    except Exception as e:
        import traceback
        return {"error": str(e), "traceback": traceback.format_exc()}


@router.post("/wildlife/download")
async def download_wildlife_model():
    """Download EfficientNet-Lite4 for wildlife/animal classification.

    Uses EfficientNet-Lite4 trained on ImageNet-1000 classes.
    - Input: 300x300 RGB float32, normalized to [-1, 1]
    - Output: 1000 ImageNet classes
    - Model size: ~50MB
    """
    import httpx
    import tarfile
    import io

    # EfficientNet-Lite4 - well-documented, reliable model
    MODEL_TAR_URL = "https://storage.googleapis.com/cloud-tpu-checkpoints/efficientnet/lite/efficientnet-lite4.tar.gz"
    LABELS_URL = "https://storage.googleapis.com/download.tensorflow.org/data/ImageNetLabels.txt"

    # Use persistent /data/models directory
    models_dir = Path("/data/models")
    models_dir.mkdir(parents=True, exist_ok=True)
    model_path = models_dir / settings.classification.wildlife_model
    labels_path = models_dir / settings.classification.wildlife_labels

    # Delete old model to force re-download
    if model_path.exists():
        model_path.unlink()
        log.info("Deleted old wildlife model for re-download")
    if labels_path.exists():
        labels_path.unlink()
        log.info("Deleted old wildlife labels for re-download")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=300.0) as client:
            # Download the EfficientNet-Lite4 tar.gz archive
            log.info("Downloading EfficientNet-Lite4 model (~50MB)...")
            model_response = await client.get(MODEL_TAR_URL, headers=headers)
            model_response.raise_for_status()

            content = model_response.content
            log.info("Downloaded archive", size_mb=len(content) / (1024 * 1024))

            # Extract the float32 TFLite model from the archive
            tflite_content = None
            with tarfile.open(fileobj=io.BytesIO(content), mode='r:gz') as tar:
                for member in tar.getmembers():
                    log.debug(f"Archive contains: {member.name}")
                    if member.name.endswith('.tflite') and 'int8' not in member.name.lower():
                        f = tar.extractfile(member)
                        if f:
                            tflite_content = f.read()
                            log.info("Found TFLite model", name=member.name, size_mb=len(tflite_content) / (1024 * 1024))
                            break

                # Fallback to any tflite file if no float model found
                if tflite_content is None:
                    for member in tar.getmembers():
                        if member.name.endswith('.tflite'):
                            f = tar.extractfile(member)
                            if f:
                                tflite_content = f.read()
                                log.info("Found TFLite model (fallback)", name=member.name, size_mb=len(tflite_content) / (1024 * 1024))
                                break

            if tflite_content is None:
                raise Exception("No TFLite model found in archive")

            with open(model_path, 'wb') as f:
                f.write(tflite_content)
            log.info("Wildlife model saved", path=str(model_path))

            # Download ImageNet labels
            log.info("Downloading ImageNet labels...")
            labels_response = await client.get(LABELS_URL, headers=headers)
            labels_response.raise_for_status()

            # ImageNet labels file has 1001 classes (background at index 0)
            lines = labels_response.text.strip().split('\n')
            all_labels = [line.strip() for line in lines if line.strip()]

            # Skip background class for EfficientNet which outputs 1000 classes
            if all_labels and all_labels[0].lower() == 'background':
                processed_labels = all_labels[1:]
                log.info("Skipped background label, using 1000 ImageNet classes")
            else:
                processed_labels = all_labels

            with open(labels_path, 'w') as f:
                for label in processed_labels:
                    f.write(f"{label}\n")

            # Reload the classifier service to pick up the new model
            classifier_service.reload_wildlife_model()

            log.info("Wildlife model downloaded and ready",
                     labels_count=len(processed_labels),
                     model_size_mb=len(tflite_content) / (1024 * 1024))
            return {
                "status": "ok",
                "message": f"Downloaded EfficientNet-Lite4 with {len(processed_labels)} labels",
                "labels_count": len(processed_labels),
                "model": "EfficientNet-Lite4",
                "input_size": "300x300"
            }

    except httpx.HTTPStatusError as e:
        log.error("Failed to download wildlife model - HTTP error", status=e.response.status_code)
        return {"status": "error", "message": f"HTTP {e.response.status_code}: Download failed"}
    except Exception as e:
        log.error("Failed to download wildlife model", error=str(e))
        return {"status": "error", "message": str(e)}


@router.post("/download")
async def download_default_model():
    """Download the default bird classifier model."""
    import httpx

    # TFLite bird classifier model URLs - using Google Coral EdgeTPU repo
    MODEL_URLS = [
        "https://raw.githubusercontent.com/google-coral/edgetpu/master/test_data/mobilenet_v2_1.0_224_inat_bird_quant.tflite",
    ]
    LABELS_URL = "https://raw.githubusercontent.com/google-coral/edgetpu/master/test_data/inat_bird_labels.txt"

    # Use persistent /data/models directory
    models_dir = Path("/data/models")
    models_dir.mkdir(parents=True, exist_ok=True)
    model_path = models_dir / "model.tflite"
    labels_path = models_dir / "labels.txt"

    # Check if model already exists
    if model_path.exists() and labels_path.exists():
        log.info("Model already exists, skipping download", path=str(model_path))
        return {
            "status": "ok",
            "message": "Model already downloaded",
            "path": str(model_path)
        }

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/octet-stream, */*',
    }

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=120.0) as client:
            # Try each model URL until one works
            model_content = None
            last_error = None

            for model_url in MODEL_URLS:
                try:
                    log.info("Trying to download model", url=model_url)
                    model_response = await client.get(model_url, headers=headers)
                    model_response.raise_for_status()

                    content = model_response.content
                    if content[:4] == b'<htm' or content[:4] == b'<!DO' or len(content) < 1000:
                        log.warning("Downloaded content appears to be HTML, trying next URL")
                        continue

                    model_content = content
                    log.info("Model downloaded successfully", size=len(content), url=model_url)
                    break
                except httpx.HTTPStatusError as e:
                    last_error = f"HTTP {e.response.status_code} from {model_url}"
                    log.warning("Model URL failed", url=model_url, status=e.response.status_code)
                    continue

            if model_content is None:
                raise Exception(f"All model download URLs failed. Last error: {last_error}")

            with open(model_path, 'wb') as f:
                f.write(model_content)

            # Download labels
            log.info("Downloading labels...")
            labels_response = await client.get(LABELS_URL, headers=headers)
            labels_response.raise_for_status()
            with open(labels_path, 'wb') as f:
                f.write(labels_response.content)

        # Process labels to extract common names
        with open(labels_path, 'r') as f:
            lines = f.readlines()

        processed_labels = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if '(' in line and ')' in line:
                start = line.rfind('(') + 1
                end = line.rfind(')')
                common_name = line[start:end].strip()
                processed_labels.append(common_name)
            else:
                parts = line.split(' ', 1)
                processed_labels.append(parts[1] if len(parts) > 1 else line)

        with open(labels_path, 'w') as f:
            for label in processed_labels:
                f.write(f"{label}\n")

        # Reload the classifier
        classifier_service._load_model()

        log.info("Model downloaded and loaded successfully")
        return {
            "status": "ok",
            "message": f"Downloaded model with {len(processed_labels)} species",
            "labels_count": len(processed_labels)
        }
    except httpx.HTTPStatusError as e:
        log.error("Failed to download model - HTTP error", status=e.response.status_code, url=str(e.request.url))
        return {"status": "error", "message": f"HTTP {e.response.status_code}: Failed to download from {e.request.url}"}
    except Exception as e:
        log.error("Failed to download model", error=str(e))
        return {"status": "error", "message": str(e)}
