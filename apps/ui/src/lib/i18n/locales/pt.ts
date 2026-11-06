import { dictionaryFromDomainFiles, type LocaleDictionary } from '../locale-partition';

export default dictionaryFromDomainFiles(
    import.meta.glob<LocaleDictionary>('./pt/*.json', { eager: true, import: 'default' })
);
