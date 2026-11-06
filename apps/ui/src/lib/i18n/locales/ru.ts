import { dictionaryFromDomainFiles, type LocaleDictionary } from '../locale-partition';

export default dictionaryFromDomainFiles(
    import.meta.glob<LocaleDictionary>('./ru/*.json', { eager: true, import: 'default' })
);
