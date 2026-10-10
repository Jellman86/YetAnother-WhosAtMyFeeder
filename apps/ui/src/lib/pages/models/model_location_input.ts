import type { ModelMetadata } from '../../api';

const SAVED_FEEDER_LOCATION_CONTRACT = 'inat2021_location_v1';

// Only the exact declared contract earns location guidance; an unknown version
// may read other inputs, so the picker says nothing rather than overclaim.
export function usesSavedFeederLocation(model: Pick<ModelMetadata, 'preprocessing'>): boolean {
    return model.preprocessing?.metadata_input === SAVED_FEEDER_LOCATION_CONTRACT;
}
