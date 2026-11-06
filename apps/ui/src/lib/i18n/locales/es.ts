import { dictionaryFromDomainFiles, type LocaleDictionary } from '../locale-partition';

export default dictionaryFromDomainFiles(
    import.meta.glob<LocaleDictionary>('./es/*.json', { eager: true, import: 'default' })
);
