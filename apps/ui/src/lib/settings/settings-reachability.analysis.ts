/**
 * A static map of the Settings page, read from its source, for the reachability test: every
 * control the page can render, and the saved-settings payload entries each control writes.
 *
 * A control is a native input, select, textarea or button, or one of the Settings input primitives,
 * at any depth below the host page. What it writes is followed back up to the host:
 * - a two-way binding (`bind:value={x}`, or a handler assigning `x`) must stay two-way at every
 *   step: `x` a `$bindable` prop, passed with `bind:` by each parent, ending at host state;
 * - a callback prop it calls (`onchange(...)`) is followed through whatever passes it, ending at
 *   the host expression it was given;
 * - a local copy is followed to the bindable prop the component syncs it into.
 * At the host, the state reached is matched against the identifiers each entry of
 * `buildSettingsPayload()` reads, through `$derived` values and called functions.
 */

export interface ControlPath {
    /** The source file holding the control. */
    file: string;
    /** Its literal id, or null when it has none. */
    id: string | null;
    /** The host's area that renders it: the former tab, or now the section. */
    areas: string[];
    /** Payload entries it writes: a field name, or the text of a spread entry. */
    entries: string[];
}

export interface SettingsMap {
    controls: ControlPath[];
    /** Every literal element id rendered below the host, with the host areas that render it. */
    ids: Record<string, string[]>;
}

type Sources = Readonly<Record<string, string>>;

const CONTROL_TAGS = new Set(['input', 'select', 'textarea', 'button', 'SettingsInput', 'SettingsSelect', 'SettingsToggle', 'SettingsSlider', 'SettingsTextarea', 'SettingsSegmented', 'SecretInput', 'Segmented']);
/** More assignments than any edit makes: a function this size reloads every setting. */
const RELOAD_WRITES = 20;
/** The input primitives are counted where they are used, not inside themselves. */
const PRIMITIVE_DIRECTORIES = /\/(?:settings\/_primitives|ui)\//;
const KEYWORDS = new Set([
    'if', 'for', 'while', 'switch', 'return', 'function', 'typeof', 'await', 'async', 'new', 'catch', 'const', 'let', 'var',
    'true', 'false', 'null', 'undefined', 'void', 'in', 'of', 'else', 'this', 'Promise', 'Math', 'Number', 'String', 'Boolean',
    'Array', 'Object', 'JSON', 'Set', 'Map', 'Date', 'console', 'window', 'document', 'event', 'e', 'v', 'next', 'value', 'checked'
]);

function resolvePath(from: string, relative: string): string {
    const parts = from.split('/').slice(0, -1);
    for (const segment of relative.split('/')) {
        if (segment === '..') parts.pop();
        else if (segment !== '.') parts.push(segment);
    }
    return parts.join('/');
}

function baseName(path: string): string {
    return path.slice(path.lastIndexOf('/') + 1).replace(/\.svelte$/, '');
}

/** The text from `open` (an opening bracket) to its match, inclusive. */
function balanced(text: string, open: number): string {
    const pairs: Record<string, string> = { '{': '}', '(': ')', '[': ']' };
    const closeFor = pairs[text[open]];
    let depth = 0;
    let quote: string | null = null;
    for (let index = open; index < text.length; index += 1) {
        const char = text[index];
        if (quote) {
            if (char === '\\') index += 1;
            else if (char === quote) quote = null;
            continue;
        }
        // A comment may hold an apostrophe or a bracket; it is not code.
        if (char === '/' && text[index + 1] === '/') {
            const end = text.indexOf('\n', index);
            index = end < 0 ? text.length : end;
            continue;
        }
        if (char === '/' && text[index + 1] === '*') {
            const end = text.indexOf('*/', index + 2);
            index = end < 0 ? text.length : end + 1;
            continue;
        }
        if (char === '"' || char === "'" || char === '`') quote = char;
        else if (char === text[open]) depth += 1;
        else if (char === closeFor) {
            depth -= 1;
            if (depth === 0) return text.slice(open, index + 1);
        }
    }
    return text.slice(open);
}

/** The opening tag starting at `start`, up to its `>`, skipping braces and attribute quotes. */
function tagAt(text: string, start: number): string {
    let depth = 0;
    let quote: string | null = null;
    for (let index = start + 1; index < text.length; index += 1) {
        const char = text[index];
        if (depth > 0) {
            if (char === '{') depth += 1;
            else if (char === '}') depth -= 1;
            continue;
        }
        if (quote) {
            if (char === quote) quote = null;
            continue;
        }
        if (char === '"') quote = char;
        else if (char === '{') depth += 1;
        else if (char === '>') return text.slice(start, index + 1);
    }
    return text.slice(start);
}

interface Parsed {
    script: string;
    markup: string;
    /** Prop name to whether it is `$bindable`. */
    props: Map<string, boolean>;
    /** Function name to its body, for functions declared in the script. */
    functions: Map<string, string>;
    /** `$derived` value name to its expression. */
    derived: Map<string, string>;
    /** Local component name to its file. */
    components: Map<string, string>;
}

function parse(path: string, text: string, loaders: ReadonlyMap<string, string>): Parsed {
    const scriptMatch = /<script(?![^>]*context="module")[^>]*>([\s\S]*?)<\/script>/.exec(text);
    const script = scriptMatch?.[1] ?? '';
    const markup = scriptMatch ? text.slice((scriptMatch.index ?? 0) + scriptMatch[0].length) : text;

    const props = new Map<string, boolean>();
    const propsAt = script.indexOf('$props()');
    if (propsAt >= 0) {
        const letAt = script.lastIndexOf('let {', propsAt);
        // Comments are dropped first: a documented prop starts with one.
        let body = balanced(script, letAt + 4).slice(1, -1).replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');
        // Generic arguments (`$bindable<Record<string, string>>`) hold commas of their own.
        for (let previous = ''; previous !== body;) {
            previous = body;
            body = body.replace(/<[^<>()]*>/g, '');
        }
        let depth = 0;
        let entry = '';
        for (const char of `${body},`) {
            if ('([{'.includes(char)) depth += 1;
            if (')]}'.includes(char)) depth -= 1;
            if (char === ',' && depth === 0) {
                const match = /^\s*(?:\.\.\.)?(\w+)(?:\s*:\s*(\w+))?/.exec(entry);
                if (match) props.set(match[2] ?? match[1], /\$bindable/.test(entry));
                entry = '';
                continue;
            }
            entry += char;
        }
    }

    const functions = new Map<string, string>();
    for (const match of script.matchAll(/function\s+(\w+)\s*(?:<[^>]*>)?\(/g)) {
        // The body follows the parameter list, which may itself hold braces (a destructured patch).
        const parameters = balanced(script, (match.index ?? 0) + match[0].length - 1);
        const brace = script.indexOf('{', (match.index ?? 0) + match[0].length - 1 + parameters.length);
        functions.set(match[1], balanced(script, brace));
    }
    for (const match of script.matchAll(/(?:const|let)\s+(\w+)\s*=\s*(?:async\s*)?(\(|\w+\s*=>)/g)) {
        let after = (match.index ?? 0) + match[0].length;
        if (match[2] === '(') {
            after = (match.index ?? 0) + match[0].length - 1 + balanced(script, (match.index ?? 0) + match[0].length - 1).length;
            const arrow = /^\s*(?::\s*[^=]+?)?=>/.exec(script.slice(after));
            if (!arrow) continue;
            after += arrow[0].length;
        }
        const rest = script.slice(after);
        const lead = /^\s*/.exec(rest)?.[0].length ?? 0;
        const lineEnd = rest.indexOf('\n');
        functions.set(match[1], rest[lead] === '{' ? balanced(script, after + lead) : rest.slice(0, lineEnd < 0 ? undefined : lineEnd));
    }

    const derived = new Map<string, string>();
    for (const match of script.matchAll(/(?:const|let)\s+(\w+)(?:\s*:\s*[^=]+?)?\s*=\s*\$derived(?:\.by)?(?:<[^>]*>)?\(/g)) {
        derived.set(match[1], balanced(script, (match.index ?? 0) + match[0].length - 1));
    }

    const components = new Map<string, string>();
    for (const match of script.matchAll(/import\s+(\w+)\s+from\s+'(\.[^']+\.svelte)'/g)) components.set(match[1], resolvePath(path, match[2]));
    for (const [name, file] of loaders) components.set(name, file);
    return { script, markup, props, functions, derived, components };
}

function identifiers(source: string): string[] {
    // A spread (`...value`) reads its operand; only a single dot is a property access.
    const text = source.replace(/\.\.\./g, ' ');
    return [...text.matchAll(/(?<![\w.$'"])([A-Za-z_$][\w$]*)/g)].map((match) => match[1]).filter((name) => !KEYWORDS.has(name));
}

/** Names a piece of code assigns or mutates, and names it calls. */
function effects(source: string): { writes: Set<string>; calls: Set<string> } {
    const text = source.replace(/\.\.\./g, ' ');
    const writes = new Set<string>();
    const calls = new Set<string>();
    for (const match of text.matchAll(/(?<![\w.$])(?<!(?:const|let|var)\s+)([A-Za-z_$][\w$]*)(?:\.[\w$]+|\[[^\]]*\])*\s*(?:=|\+=|-=|\|\|=|\?\?=)(?![=>])/g)) writes.add(match[1]);
    for (const match of text.matchAll(/(?<![\w.$])([A-Za-z_$][\w$]*)\.(?:push|splice|pop|shift|unshift|set|delete|add)\(/g)) writes.add(match[1]);
    for (const match of text.matchAll(/(?<![\w.$])([A-Za-z_$][\w$]*)\s*(?:\?\.)?\(/g)) if (!KEYWORDS.has(match[1])) calls.add(match[1]);
    return { writes, calls };
}

/** The attributes of a tag: name, whether it is `bind:`, and its expression text (or null). */
function attributes(tag: string): Array<{ name: string; bind: boolean; expression: string | null }> {
    const out: Array<{ name: string; bind: boolean; expression: string | null }> = [];
    const body = tag.replace(/^<[\w.-]+/, '').replace(/\/?>$/, '');
    let index = 0;
    while (index < body.length) {
        if (/\s/.test(body[index])) { index += 1; continue; }
        if (body[index] === '{') {
            const block = balanced(body, index);
            const inner = block.slice(1, -1).trim();
            if (/^\w+$/.test(inner)) out.push({ name: inner, bind: false, expression: inner });
            index += block.length;
            continue;
        }
        const match = /^(bind:)?([\w:-]+)/.exec(body.slice(index));
        if (!match) { index += 1; continue; }
        index += match[0].length;
        let expression: string | null = null;
        if (body[index] === '=') {
            index += 1;
            if (body[index] === '{') {
                const block = balanced(body, index);
                expression = block.slice(1, -1);
                index += block.length;
            } else if (body[index] === '"') {
                const end = body.indexOf('"', index + 1);
                expression = null;
                index = end + 1;
            }
        } else if (match[1]) {
            expression = match[2];
        }
        out.push({ name: match[2], bind: Boolean(match[1]), expression });
    }
    return out;
}

/** The keys of a `props={{ … }}` object with each value's text (`...name` for a spread). */
function propsObject(expression: string): Map<string, string> {
    const inner = expression.trim().replace(/^\{/, '').replace(/\}$/, '');
    const out = new Map<string, string>();
    let depth = 0;
    let entry = '';
    for (const char of `${inner},`) {
        if ('([{'.includes(char)) depth += 1;
        if (')]}'.includes(char)) depth -= 1;
        if (char === ',' && depth === 0) {
            const text = entry.trim();
            if (text.startsWith('...')) out.set(text, text.slice(3));
            else if (text) {
                const colon = /^(\w+)\s*:\s*([\s\S]*)$/.exec(text);
                if (colon) out.set(colon[1], colon[2]);
                else out.set(text, text);
            }
            entry = '';
            continue;
        }
        entry += char;
    }
    return out;
}

interface Need {
    kind: 'bind' | 'call';
    name: string;
}

export function analyseSettings(sources: Sources, host: string): SettingsMap {
    // Part loaders: `const loadX = lazyComponent(() => import('…svelte'))`, in any module.
    const loaderFiles = new Map<string, Map<string, string>>();
    for (const [path, text] of Object.entries(sources)) {
        const own = new Map<string, string>();
        for (const match of text.matchAll(/(load\w+)\s*=\s*lazyComponent\(\(\)\s*=>\s*import\('([^']+\.svelte)'\)\)/g)) own.set(match[1], resolvePath(path, match[2]));
        loaderFiles.set(path, own);
    }
    const loadersFor = (path: string): Map<string, string> => {
        const out = new Map(loaderFiles.get(path) ?? []);
        for (const match of (sources[path] ?? '').matchAll(/import\s*\{([^}]*)\}\s*from\s*'(\.[^']+)'/g)) {
            const module = resolvePath(path, match[2]);
            const target = loaderFiles.get(`${module}.ts`);
            if (!target) continue;
            for (const name of match[1].split(',').map((part) => part.trim().split(/\s+as\s+/).pop() ?? '')) {
                const file = target.get(name);
                if (file) out.set(name, file);
            }
        }
        return out;
    };

    const parsed = new Map<string, Parsed>();
    const get = (path: string): Parsed | null => {
        if (!(path in sources)) return null;
        if (!parsed.has(path)) parsed.set(path, parse(path, sources[path], loadersFor(path)));
        return parsed.get(path) ?? null;
    };

    // Every component file the host can render, at any depth.
    const tree = new Set<string>();
    const queue = [host];
    while (queue.length > 0) {
        const path = queue.pop() as string;
        if (tree.has(path)) continue;
        const file = get(path);
        if (!file) continue;
        tree.add(path);
        for (const child of file.components.values()) queue.push(child);
    }

    // Where each component is rendered: the parent file and the opening tag that renders it.
    const parents = new Map<string, Array<{ parent: string; tag: string; at: number }>>();
    for (const path of tree) {
        const file = get(path) as Parsed;
        for (const match of file.markup.matchAll(/<([A-Z][\w.]*)\b/g)) {
            const tag = tagAt(file.markup, match.index ?? 0);
            let child: string | undefined;
            if (match[1] === 'LazyRoute') {
                const loader = /loader=\{(\w+)\}/.exec(tag)?.[1];
                if (!loader || !/\bprops=\{/.test(tag)) continue;
                child = file.components.get(loader);
            } else {
                child = file.components.get(match[1]) ?? [...file.components.values()].find((candidate) => baseName(candidate) === match[1]);
            }
            if (!child || !tree.has(child)) continue;
            const list = parents.get(child) ?? [];
            list.push({ parent: path, tag, at: match.index ?? 0 });
            parents.set(child, list);
        }
    }

    // The host's area around a position in its markup: the former tab or the section.
    const hostFile = get(host) as Parsed;
    const areaAt = (at: number): string | null => {
        const before = hostFile.markup.slice(0, at);
        const matches = [...before.matchAll(/active(?:Tab|Section)\s*===\s*'(\w+)'/g)];
        return matches.length > 0 ? matches[matches.length - 1][1] : null;
    };
    const areasMemo = new Map<string, Set<string>>();
    const areasOf = (path: string, seen = new Set<string>()): Set<string> => {
        if (areasMemo.has(path)) return areasMemo.get(path) as Set<string>;
        const out = new Set<string>();
        if (seen.has(path)) return out;
        seen.add(path);
        for (const { parent, at } of parents.get(path) ?? []) {
            if (parent === host) {
                const area = areaAt(at);
                if (area) out.add(area);
            } else for (const area of areasOf(parent, seen)) out.add(area);
        }
        areasMemo.set(path, out);
        return out;
    };

    /** What code in a file writes, with its local functions followed. */
    const expand = (file: Parsed, text: string): { writes: Set<string>; calls: Set<string> } => {
        const writes = new Set<string>();
        const calls = new Set<string>();
        const pending = [text];
        const visited = new Set<string>();
        while (pending.length > 0) {
            const found = effects(pending.pop() as string);
            for (const name of found.writes) writes.add(name);
            for (const name of found.calls) {
                calls.add(name);
                const body = file.functions.get(name);
                if (!body || visited.has(name)) continue;
                visited.add(name);
                // A function that assigns this many values puts the saved settings back (a reload
                // or Discard); it edits none of them, so it is not followed.
                if (effects(body).writes.size > RELOAD_WRITES) continue;
                pending.push(body);
            }
        }
        return { writes, calls };
    };

    /** The props a set of writes and calls reaches in a component, local copies followed. */
    const needsIn = (file: Parsed, writes: Iterable<string>, calls: Iterable<string>): Need[] => {
        const needs: Need[] = [];
        const bindable = [...file.props].filter(([, isBindable]) => isBindable).map(([name]) => name);
        for (const name of writes) {
            if (file.props.get(name)) needs.push({ kind: 'bind', name });
            else if (!file.props.has(name)) {
                // A local copy: the bindable props assigned on a line that reads it.
                for (const line of file.script.split('\n')) {
                    if (!new RegExp(`\\b${name}\\b`).test(line)) continue;
                    for (const prop of bindable) if (new RegExp(`(?<![\\w.])${prop}\\s*=(?![=>])`).test(line)) needs.push({ kind: 'bind', name: prop });
                }
            }
        }
        for (const name of calls) if (file.props.has(name) && !file.props.get(name)) needs.push({ kind: 'call', name });
        return needs;
    };

    /** Host state a need in a component reaches, following every parent that renders it. */
    const resolve = (path: string, need: Need, seen: Set<string>): Set<string> => {
        const reached = new Set<string>();
        const key = `${path}|${need.kind}|${need.name}`;
        if (seen.has(key)) return reached;
        seen.add(key);
        for (const { parent, tag } of parents.get(path) ?? []) {
            const parentFile = get(parent) as Parsed;
            const isLazy = tag.startsWith('<LazyRoute');
            let passed: { bind: boolean; expression: string } | null = null;
            if (isLazy) {
                const object = attributes(tag).find((attribute) => attribute.name === 'props')?.expression;
                const value = object ? propsObject(object).get(need.name) : undefined;
                if (value !== undefined) passed = { bind: false, expression: value };
            } else {
                const attribute = attributes(tag).find((candidate) => candidate.name === need.name && candidate.expression !== null);
                if (attribute?.expression) passed = { bind: attribute.bind, expression: attribute.expression };
            }
            if (!passed) continue;
            if (need.kind === 'bind') {
                // A two-way value must be passed two-way, all the way up.
                if (!passed.bind) continue;
                const root = /^\s*([A-Za-z_$][\w$]*)/.exec(passed.expression)?.[1];
                if (!root) continue;
                if (parent === host) reached.add(root);
                else for (const next of needsIn(parentFile, [root], [])) for (const name of resolve(parent, next, seen)) reached.add(name);
                continue;
            }
            const expression = passed.expression.trim();
            const direct = /^[A-Za-z_$][\w$]*$/.test(expression) ? expression : null;
            const { writes, calls } = expand(parentFile, direct ? `${direct}()` : expression);
            if (parent === host) {
                for (const name of writes) reached.add(name);
                for (const name of calls) reached.add(name);
                continue;
            }
            for (const next of needsIn(parentFile, writes, calls)) for (const name of resolve(parent, next, seen)) reached.add(name);
        }
        return reached;
    };

    // The payload entries and the host state each reads, `$derived` values followed.
    const payloadBody = (() => {
        const at = hostFile.script.indexOf('function buildSettingsPayload');
        const returnAt = hostFile.script.indexOf('return {', at);
        return balanced(hostFile.script, returnAt + 'return '.length).slice(1, -1).replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/[^\n]*$/gm, '');
    })();
    const entries = new Map<string, Set<string>>();
    const readsOf = (text: string): Set<string> => {
        const out = new Set<string>();
        const pending = identifiers(text);
        while (pending.length > 0) {
            const name = pending.pop() as string;
            if (out.has(name)) continue;
            out.add(name);
            const derivedExpression = hostFile.derived.get(name);
            if (derivedExpression) pending.push(...identifiers(derivedExpression));
        }
        return out;
    };
    {
        let depth = 0;
        let entry = '';
        for (const char of `${payloadBody},`) {
            if ('([{'.includes(char)) depth += 1;
            if (')]}'.includes(char)) depth -= 1;
            if (char === ',' && depth === 0) {
                const text = entry.replace(/\s+/g, ' ').trim();
                if (text.startsWith('...')) entries.set(text, readsOf(text.slice(3)));
                else if (text) {
                    const match = /^(\w+)\s*:\s*([\s\S]*)$/.exec(text);
                    if (match) entries.set(match[1], readsOf(match[2]));
                }
                entry = '';
                continue;
            }
            entry += char;
        }
    }
    // Host functions reached by a callback: what they write counts as reached.
    const hostReach = (names: Set<string>): Set<string> => {
        const out = new Set(names);
        for (const name of names) {
            if (hostFile.functions.has(name)) for (const written of expand(hostFile, `${name}()`).writes) out.add(written);
        }
        return out;
    };

    /** The text that defines a list a component loops over: its `$derived` or its declaration. */
    const listDefinition = (file: Parsed, name: string): string | null => {
        const derivedExpression = file.derived.get(name);
        if (derivedExpression) return derivedExpression;
        const declaration = new RegExp(`(?:const|let)\\s+${name}\\b[^=]*=\\s*`).exec(file.script);
        if (!declaration) return null;
        const start = (declaration.index ?? 0) + declaration[0].length;
        const open = file.script.slice(start).search(/[[({]/);
        return open < 0 ? null : balanced(file.script, start + open);
    };

    /** The list an `{#each … as item}` block loops over: an inline array, or the declared list. */
    const eachListFor = (file: Parsed, item: string): string | null => {
        const each = new RegExp(`\\{#each\\s+`, 'g');
        for (const match of file.markup.matchAll(each)) {
            const start = (match.index ?? 0) + match[0].length;
            const listText = file.markup[start] === '[' ? balanced(file.markup, start) : /^[A-Za-z_$][\w$.]*/.exec(file.markup.slice(start))?.[0] ?? '';
            if (!new RegExp(`^\\s*as\\s+${item}\\b`).test(file.markup.slice(start + listText.length))) continue;
            return listText.startsWith('[') ? listText : listDefinition(file, listText);
        }
        return null;
    };

    const controls: ControlPath[] = [];
    const ids: Record<string, string[]> = {};
    for (const path of tree) {
        if (path === host) continue;
        const file = get(path) as Parsed;
        const areas = [...areasOf(path)].sort();
        const primitive = PRIMITIVE_DIRECTORIES.test(path);
        for (const match of file.markup.matchAll(/\bid="([a-z][a-z0-9-]*)"/g)) {
            ids[match[1]] = [...new Set([...(ids[match[1]] ?? []), ...areas])].sort();
        }
        for (const match of file.markup.matchAll(/<([A-Za-z][\w.]*)\b/g)) {
            if (primitive || !CONTROL_TAGS.has(match[1])) continue;
            const tag = tagAt(file.markup, match.index ?? 0);
            if (match[1] === 'input' && /type="(?:hidden|file)"/.test(tag)) continue;
            const writes = new Set<string>();
            const calls = new Set<string>();
            for (const attribute of attributes(tag)) {
                if (attribute.bind && attribute.name !== 'this' && attribute.expression) {
                    const root = /^\s*([A-Za-z_$][\w$]*)/.exec(attribute.expression)?.[1];
                    if (root) writes.add(root);
                } else if (/^on/.test(attribute.name) && attribute.expression) {
                    const expression = attribute.expression.trim();
                    const found = expand(file, /^[A-Za-z_$][\w$]*$/.test(expression) ? `${expression}()` : expression);
                    for (const name of found.writes) writes.add(name);
                    for (const name of found.calls) calls.add(name);
                    // A method on an `{#each}` item (`entity.set(v)`, or `entity.set` passed on): what
                    // the list's items do.
                    for (const call of expression.matchAll(/(?<![\w.$])([A-Za-z_$][\w$]*)\.(\w+)/g)) {
                        const definition = eachListFor(file, call[1]);
                        if (!definition) continue;
                        const items = expand(file, definition);
                        for (const name of items.writes) writes.add(name);
                        for (const name of items.calls) calls.add(name);
                    }
                }
            }
            const reached = new Set<string>();
            for (const need of needsIn(file, writes, calls)) for (const name of resolve(path, need, new Set())) reached.add(name);
            const hostState = hostReach(reached);
            const reachedEntries = [...entries].filter(([, reads]) => [...reads].some((name) => hostState.has(name))).map(([label]) => label).sort();
            controls.push({ file: path, id: /\bid="([a-z][a-z0-9-]*)"/.exec(tag)?.[1] ?? null, areas, entries: reachedEntries });
        }
    }
    controls.sort((a, b) => `${a.file}#${a.id ?? ''}`.localeCompare(`${b.file}#${b.id ?? ''}`));
    return { controls, ids };
}
