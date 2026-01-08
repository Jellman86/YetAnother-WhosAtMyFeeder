import pytest
import numpy as np
import sys
from unittest.mock import MagicMock, patch, mock_open
from PIL import Image

# Mock model_manager before it's imported by anything
mock_mm = MagicMock()
mock_mm.model_manager = MagicMock()
mock_mm.model_manager.get_active_model_paths.return_value = ("model.tflite", "labels.txt", 224)
mock_mm.model_manager.active_model_id = "default"
mock_mm.REMOTE_REGISTRY = []
sys.modules["app.services.model_manager"] = mock_mm

from app.services.classifier_service import ClassifierService, ModelInstance, ONNXModelInstance

@pytest.fixture
def mock_tflite():
    with patch("app.services.classifier_service.tflite") as mock:
        yield mock

@pytest.fixture
def mock_os_path_exists():
    with patch("os.path.exists") as mock:
        mock.return_value = True
        yield mock

def test_model_instance_load(mock_tflite, mock_os_path_exists):
    # Mock labels file content
    m = mock_open(read_data="Bird A\nBird B\n")
    with patch("builtins.open", m):
        model = ModelInstance("test", "model.tflite", "labels.txt")
        success = model.load()
        
    assert success is True
    assert model.loaded is True
    assert len(model.labels) == 2
    assert model.labels[0] == "Bird A"
    mock_tflite.Interpreter.assert_called_with(model_path="model.tflite")

def test_model_instance_classify(mock_tflite, mock_os_path_exists):
    # Mock labels and interpreter
    m = mock_open(read_data="Bird A\nBird B\n")
    with patch("builtins.open", m):
        model = ModelInstance("test", "model.tflite", "labels.txt")
        model.load()
    
    # Mock interpreter behavior
    interpreter = mock_tflite.Interpreter.return_value
    interpreter.get_input_details.return_value = [{'shape': [1, 224, 224, 3], 'dtype': np.float32, 'index': 0}]
    interpreter.get_output_details.return_value = [{'dtype': np.float32, 'index': 0}]
    
    # Mock output tensor (probabilities)
    # [Bird A score, Bird B score]
    mock_output = np.array([[0.8, 0.2]], dtype=np.float32)
    interpreter.get_tensor.return_value = mock_output
    
    # Test image
    img = Image.new('RGB', (100, 100))
    results = model.classify(img)
    
    assert len(results) > 0
    assert results[0]['label'] == "Bird A"
    assert results[0]['score'] == pytest.approx(0.8)

@pytest.mark.asyncio
async def test_classifier_service_init(mock_tflite, mock_os_path_exists):
    # Define a side effect that sets the loaded attribute to True
    def mock_load(self):
        self.loaded = True
        return True

    # Use autospec=True so 'self' is passed to the side_effect
    with patch("app.services.classifier_service.ModelInstance.load", autospec=True, side_effect=mock_load):
        service = ClassifierService()
        assert "bird" in service._models
        assert service.model_loaded is True

@pytest.mark.asyncio
async def test_classifier_service_classify_async(mock_tflite, mock_os_path_exists):
    with patch("app.services.classifier_service.ModelInstance.load", return_value=True), \
         patch("app.services.classifier_service.ModelInstance.classify") as mock_classify:
        
        mock_classify.return_value = [{"label": "Robin", "score": 0.9}]
        service = ClassifierService()
        
        img = Image.new('RGB', (100, 100))
        results = await service.classify_async(img)
        
        assert results[0]["label"] == "Robin"
        mock_classify.assert_called_once()
