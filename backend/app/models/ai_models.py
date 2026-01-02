from pydantic import BaseModel
from typing import List, Optional

class ModelMetadata(BaseModel):
    id: str
    name: str
    description: str
    architecture: str  # e.g., "MobileNetV2", "EfficientNet-Lite4"
    file_size_mb: float
    accuracy_tier: str # "High", "Medium", "Low"
    inference_speed: str # "Fast", "Medium", "Slow"
    download_url: str
    labels_url: str
    input_size: int = 224
    
class InstalledModel(BaseModel):
    id: str
    path: str
    labels_path: str
    is_active: bool
    metadata: Optional[ModelMetadata] = None
