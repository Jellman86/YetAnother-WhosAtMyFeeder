from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime

class YAWAMFBaseModel(BaseModel):
    model_config = ConfigDict(protected_namespaces=())


class ClassificationInputContext(YAWAMFBaseModel):
    model_config = ConfigDict(protected_namespaces=(), extra="allow")
    is_cropped: StrictBool = False


class CropGeneratorConfig(YAWAMFBaseModel):
    model_config = ConfigDict(protected_namespaces=(), extra="allow")
    enabled: StrictBool = False
    input_context: Optional[ClassificationInputContext] = None


class ModelMetadata(YAWAMFBaseModel):
    id: str
    name: str
    description: str
    architecture: str  # e.g., "MobileNetV2", "EfficientNet-Lite4"
    file_size_mb: float
    accuracy_tier: str # "High", "Medium", "Low"
    inference_speed: str # "Fast", "Medium", "Slow"
    download_url: str
    weights_url: Optional[str] = None
    labels_url: str
    model_config_url: Optional[str] = None
    input_size: int = 224
    runtime: Optional[str] = None
    preprocessing: Optional[Dict[str, Any]] = None
    supported_inference_providers: Optional[List[str]] = None
    tier: str
    taxonomy_scope: str
    recommended_for: str
    estimated_ram_mb: Optional[int] = None
    advanced_only: bool = False
    sort_order: int = 0
    status: str = "stable"
    notes: Optional[str] = None
    family_id: Optional[str] = None
    default_region: Optional[str] = None
    region_variants: Optional[Dict[str, Dict[str, Any]]] = None
    label_grouping: Optional[Dict[str, Any]] = None
    crop_generator: CropGeneratorConfig = Field(default_factory=CropGeneratorConfig)

    @field_validator("crop_generator", mode="before")
    @classmethod
    def _normalize_crop_generator(cls, value: Any) -> CropGeneratorConfig:
        if isinstance(value, CropGeneratorConfig):
            return value
        if value is None:
            return CropGeneratorConfig()
        try:
            return CropGeneratorConfig.model_validate(value)
        except Exception:
            return CropGeneratorConfig()
    
class InstalledModel(YAWAMFBaseModel):
    id: str
    path: str
    labels_path: str
    is_active: bool
    metadata: Optional[ModelMetadata] = None

class DownloadProgress(YAWAMFBaseModel):
    model_id: str
    status: str # "pending", "downloading", "completed", "error"
    progress: float # 0-100
    message: Optional[str] = None
    error: Optional[str] = None

class AIUsageLog(YAWAMFBaseModel):
    id: Optional[int] = None
    timestamp: datetime
    provider: str
    model: str
    feature: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
