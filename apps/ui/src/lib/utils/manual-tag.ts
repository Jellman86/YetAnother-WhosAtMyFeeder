import type { Detection, UpdateDetectionResult } from '../api';

export function applyManualTagResult(detection: Detection, result: UpdateDetectionResult): Detection {
    const identificationChanged = result.status === 'updated';
    return {
        ...detection,
        display_name: result.new_species,
        category_name: result.category_name ?? result.scientific_name ?? result.new_species,
        scientific_name: result.scientific_name,
        common_name: result.common_name,
        taxa_id: result.taxa_id,
        manual_tagged: result.manual_tagged,
        ai_analysis: identificationChanged ? null : detection.ai_analysis,
        ai_analysis_timestamp: identificationChanged ? null : detection.ai_analysis_timestamp
    };
}
