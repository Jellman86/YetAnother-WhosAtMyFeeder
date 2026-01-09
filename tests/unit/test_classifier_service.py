import pytest
import numpy as np
from unittest.mock import MagicMock, patch, mock_open
from PIL import Image


@pytest.fixture
def sample_image():
    """Create a sample PIL Image for testing."""
    return Image.new('RGB', (224, 224), color='red')


@pytest.fixture
def mock_tflite_interpreter():
    """Mock TFLite interpreter."""
    interpreter = MagicMock()
    interpreter.allocate_tensors = MagicMock()
    interpreter.get_input_details = MagicMock(return_value=[{
        'index': 0,
        'shape': [1, 224, 224, 3],
        'dtype': np.float32
    }])
    interpreter.get_output_details = MagicMock(return_value=[{
        'index': 0,
        'dtype': np.float32,
        'quantization_parameters': {}
    }])
    interpreter.set_tensor = MagicMock()
    interpreter.invoke = MagicMock()
    interpreter.get_tensor = MagicMock(return_value=np.random.rand(1, 10))
    return interpreter


class TestModelInstance:
    """Unit tests for ModelInstance class."""

    def test_model_load_success(self, mock_tflite_interpreter):
        """Test successful model loading."""
        from app.services.classifier_service import ModelInstance

        with patch('app.services.classifier_service.tflite') as mock_tflite, \
             patch('builtins.open', mock_open(read_data="label1\nlabel2\nlabel3")), \
             patch('os.path.exists', return_value=True):

            mock_tflite.Interpreter = MagicMock(return_value=mock_tflite_interpreter)

            model = ModelInstance("test", "/path/to/model.tflite", "/path/to/labels.txt")
            result = model.load()

            assert result is True
            assert model.loaded is True
            assert len(model.labels) == 3
            assert model.error is None

    def test_model_load_file_not_found(self):
        """Test model loading when file doesn't exist."""
        from app.services.classifier_service import ModelInstance

        with patch('builtins.open', mock_open(read_data="label1\nlabel2")), \
             patch('os.path.exists', side_effect=[True, False]):  # labels exist, model doesn't

            model = ModelInstance("test", "/path/to/nonexistent.tflite", "/path/to/labels.txt")
            result = model.load()

            assert result is False
            assert model.loaded is False
            assert model.error is not None
            assert "not found" in model.error

    def test_model_cleanup(self, mock_tflite_interpreter):
        """Test model cleanup releases resources."""
        from app.services.classifier_service import ModelInstance

        with patch('app.services.classifier_service.tflite') as mock_tflite, \
             patch('builtins.open', mock_open(read_data="label1\nlabel2")), \
             patch('os.path.exists', return_value=True):

            mock_tflite.Interpreter = MagicMock(return_value=mock_tflite_interpreter)

            model = ModelInstance("test", "/path/to/model.tflite", "/path/to/labels.txt")
            model.load()

            assert model.interpreter is not None
            assert model.loaded is True

            # Cleanup
            model.cleanup()

            assert model.interpreter is None
            assert model.loaded is False

    def test_classify_with_loaded_model(self, mock_tflite_interpreter, sample_image):
        """Test classification with a loaded model."""
        from app.services.classifier_service import ModelInstance

        with patch('app.services.classifier_service.tflite') as mock_tflite, \
             patch('builtins.open', mock_open(read_data="bird1\nbird2\nbird3")), \
             patch('os.path.exists', return_value=True):

            mock_tflite.Interpreter = MagicMock(return_value=mock_tflite_interpreter)

            model = ModelInstance("test", "/path/to/model.tflite", "/path/to/labels.txt")
            model.load()

            results = model.classify(sample_image)

            assert len(results) > 0
            assert all('label' in r and 'score' in r and 'index' in r for r in results)


class TestClassifierService:
    """Unit tests for ClassifierService."""

    def test_reload_bird_model_calls_cleanup(self):
        """Test that reload_bird_model calls cleanup on old model."""
        from app.services.classifier_service import ClassifierService

        with patch('app.services.classifier_service.ModelInstance') as MockModel, \
             patch('app.services.model_manager.model_manager') as mock_manager:

            # Mock model manager
            mock_manager.get_active_model_paths = MagicMock(
                return_value=("/model.tflite", "/labels.txt", 224)
            )
            mock_manager.active_model_id = "test-model"

            # Mock model instance
            old_model = MagicMock()
            old_model.cleanup = MagicMock()
            old_model.load = MagicMock()

            new_model = MagicMock()
            new_model.load = MagicMock()

            MockModel.side_effect = [old_model, new_model]

            service = ClassifierService()

            # Verify old model is loaded
            assert service._models.get("bird") == old_model

            # Reload
            service.reload_bird_model()

            # Verify cleanup was called on old model
            old_model.cleanup.assert_called_once()

            # Verify new model is now active
            assert service._models.get("bird") == new_model

    @patch('cv2.VideoCapture')
    def test_classify_video_releases_capture_on_error(self, mock_video_capture):
        """Test that VideoCapture is always released even on error (memory leak fix)."""
        from app.services.classifier_service import ClassifierService

        # Mock VideoCapture that raises an error during processing
        mock_cap = MagicMock()
        mock_cap.isOpened = MagicMock(return_value=True)
        mock_cap.get = MagicMock(side_effect=[100, 30.0])  # total_frames, fps
        mock_cap.set = MagicMock()
        mock_cap.read = MagicMock(side_effect=Exception("Test error"))
        mock_cap.release = MagicMock()

        mock_video_capture.return_value = mock_cap

        with patch('app.services.classifier_service.ModelInstance') as MockModel, \
             patch('app.services.model_manager.model_manager') as mock_manager:

            mock_manager.get_active_model_paths = MagicMock(
                return_value=("/model.tflite", "/labels.txt", 224)
            )
            mock_manager.active_model_id = "test-model"

            mock_model = MagicMock()
            mock_model.load = MagicMock()
            mock_model.loaded = True
            mock_model.labels = ["bird1", "bird2"]
            MockModel.return_value = mock_model

            service = ClassifierService()

            # Call classify_video - should handle error gracefully
            result = service.classify_video("/tmp/test.mp4")

            # Verify release() was called despite error (memory leak fix)
            mock_cap.release.assert_called_once()

            # Should return empty list on error
            assert result == []

    @patch('cv2.VideoCapture')
    def test_classify_video_releases_capture_on_success(self, mock_video_capture):
        """Test that VideoCapture is released on successful classification."""
        from app.services.classifier_service import ClassifierService

        # Mock successful video capture
        mock_cap = MagicMock()
        mock_cap.isOpened = MagicMock(return_value=True)
        mock_cap.get = MagicMock(side_effect=[100, 30.0])  # total_frames, fps
        mock_cap.set = MagicMock()
        mock_cap.read = MagicMock(return_value=(True, np.zeros((224, 224, 3), dtype=np.uint8)))
        mock_cap.release = MagicMock()

        mock_video_capture.return_value = mock_cap

        with patch('app.services.classifier_service.ModelInstance') as MockModel, \
             patch('app.services.model_manager.model_manager') as mock_manager:

            mock_manager.get_active_model_paths = MagicMock(
                return_value=("/model.tflite", "/labels.txt", 224)
            )
            mock_manager.active_model_id = "test-model"

            mock_model = MagicMock()
            mock_model.load = MagicMock()
            mock_model.loaded = True
            mock_model.labels = ["bird1", "bird2"]
            mock_model.classify_raw = MagicMock(return_value=np.array([0.9, 0.1]))
            MockModel.return_value = mock_model

            service = ClassifierService()

            # Call classify_video
            result = service.classify_video("/tmp/test.mp4", max_frames=5)

            # Verify release() was called (memory leak fix)
            mock_cap.release.assert_called_once()

    @patch('cv2.VideoCapture')
    def test_classify_video_releases_capture_when_no_frames(self, mock_video_capture):
        """Test that VideoCapture is released when video has no frames."""
        from app.services.classifier_service import ClassifierService

        mock_cap = MagicMock()
        mock_cap.isOpened = MagicMock(return_value=True)
        mock_cap.get = MagicMock(side_effect=[0, 30.0])  # No frames!
        mock_cap.release = MagicMock()

        mock_video_capture.return_value = mock_cap

        with patch('app.services.classifier_service.ModelInstance') as MockModel, \
             patch('app.services.model_manager.model_manager') as mock_manager:

            mock_manager.get_active_model_paths = MagicMock(
                return_value=("/model.tflite", "/labels.txt", 224)
            )
            mock_manager.active_model_id = "test-model"

            mock_model = MagicMock()
            mock_model.load = MagicMock()
            mock_model.loaded = True
            MockModel.return_value = mock_model

            service = ClassifierService()
            result = service.classify_video("/tmp/test.mp4")

            # Verify release() was called (memory leak fix)
            mock_cap.release.assert_called_once()
            assert result == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
