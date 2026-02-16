import { h, render } from 'https://esm.sh/preact@10.19.3';
import { useState, useEffect, useMemo, useCallback } from 'https://esm.sh/preact@10.19.3/hooks';
import { html } from 'https://esm.sh/htm/preact@10.19.3';
import { store } from './store.js';
import { Header, Hero, ControlBar, ArtifactCard, Footer, Toast } from './components.js';

const App = () => {
    const [loading, setLoading] = useState(true);
    const [query, setQuery] = useState('');
    const [filterType, setFilterType] = useState(localStorage.getItem('gatherx_last_filter') || 'ALL');
    const [sortOption, setSortOption] = useState(localStorage.getItem('gatherx_last_sort') || 'date_desc');
    const [stats, setStats] = useState({ totalFiles: 0, totalSize: '0 B', lastUpdated: '-' });
    const [data, setData] = useState([]);

    // Theme Management
    const [theme, setTheme] = useState(localStorage.getItem('theme') || 'dark');

    // Toast State
    const [toast, setToast] = useState(null);

    // Initialize Theme
    useEffect(() => {
        if (theme === 'dark') {
            document.documentElement.classList.add('dark');
        } else {
            document.documentElement.classList.remove('dark');
        }
        localStorage.setItem('theme', theme);
    }, [theme]);

    const toggleTheme = () => {
        setTheme(prev => prev === 'dark' ? 'light' : 'dark');
    };

    // Initialize Data
    useEffect(() => {
        const init = async () => {
            await store.init();
            setLoading(false);
            if (store.data) {
                setData(store.files);
                setStats(store.getStats());
            }
        };
        init();
    }, []);

    // Filter, Search, and Sort Logic
    const processedFiles = useMemo(() => {
        let result = data;

        // Search
        if (query) {
            // Re-initialize fuse if needed (e.g. data updated)
            if (!store.fuse) {
                store._processData(data); // Ensures fuse is ready
            }
            if (store.fuse) {
                result = store.fuse.search(query).map(r => r.item);
            }
        }

        // Filter
        if (filterType !== 'ALL') {
            result = result.filter(file => file.type === filterType);
        }

        // Sort
        if (sortOption) {
            result = [...result].sort((a, b) => {
                switch (sortOption) {
                    case 'date_desc':
                        return new Date(b.last_modified) - new Date(a.last_modified);
                    case 'date_asc':
                        return new Date(a.last_modified) - new Date(b.last_modified);
                    case 'name_asc':
                        return a.filename.localeCompare(b.filename);
                    case 'size_desc':
                        return b.size - a.size;
                    default:
                        return 0;
                }
            });
        }

        return result;
    }, [query, filterType, sortOption, data]);

    // Unique types for filter bar
    const types = useMemo(() => {
        const unique = new Set(data.map(f => f.type));
        return Array.from(unique).sort();
    }, [data]);

    // Save preferences
    useEffect(() => {
        localStorage.setItem('gatherx_last_filter', filterType);
    }, [filterType]);

    useEffect(() => {
        localStorage.setItem('gatherx_last_sort', sortOption);
    }, [sortOption]);

    // Handle Toast
    const showToast = useCallback((msg, type = 'success') => {
        setToast({ message: msg, type });
        setTimeout(() => setToast(null), 3000);
    }, []);

    // Copy Handler
    const handleCopy = useCallback((text, btn) => {
        navigator.clipboard.writeText(new URL(text, window.location.href).href).then(() => {
            showToast('Link copied to clipboard!');

            // Temporary visual feedback on button
            const originalHTML = btn.innerHTML;
            btn.innerHTML = '<i data-lucide="check" class="w-5 h-5 text-green-500"></i>';
            setTimeout(() => {
                btn.innerHTML = originalHTML;
                if (window.lucide) window.lucide.createIcons();
            }, 2000);
        }).catch(err => {
            showToast('Failed to copy link', 'error');
        });
    }, [showToast]);

    // Re-run icons
    useEffect(() => {
        if (!loading) {
            setTimeout(() => {
                if (window.lucide) window.lucide.createIcons();
            }, 100);
        }
    }, [processedFiles, loading, theme]);

    if (loading) {
        return html`
            <div class="flex items-center justify-center h-screen bg-gray-50 dark:bg-gray-900 transition-colors duration-300">
                <div class="flex flex-col items-center gap-4">
                    <i data-lucide="loader-2" class="w-12 h-12 text-brand-500 animate-spin"></i>
                    <p class="text-sm text-gray-400 font-mono animate-pulse">Loading Artifacts...</p>
                </div>
            </div>
        `;
    }

    return html`
        <div class="min-h-screen flex flex-col bg-gray-50 dark:bg-gray-900 font-sans text-gray-900 dark:text-gray-100 transition-colors duration-300 selection:bg-brand-500 selection:text-white">

            <${Header}
                onSearch=${setQuery}
                stats=${stats}
                theme=${theme}
                onToggleTheme=${toggleTheme}
            />

            <main class="flex-grow w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pb-20">

                <${Hero} />

                <${ControlBar}
                    types=${types}
                    activeType=${filterType}
                    onSelectType=${setFilterType}
                    sortOption=${sortOption}
                    onSortChange=${setSortOption}
                />

                ${processedFiles.length === 0 ? html`
                    <div class="text-center py-24 bg-white dark:bg-gray-800/50 rounded-3xl border border-dashed border-gray-300 dark:border-gray-700 animate-fade-in">
                        <div class="inline-flex items-center justify-center w-20 h-20 rounded-full bg-gray-100 dark:bg-gray-800 mb-6">
                            <i data-lucide="search-x" class="w-10 h-10 text-gray-400"></i>
                        </div>
                        <h3 class="text-xl font-bold text-gray-900 dark:text-gray-100">No artifacts found</h3>
                        <p class="mt-2 text-gray-500 dark:text-gray-400 max-w-sm mx-auto">
                            We couldn't find anything matching your search. Try adjusting your filters or keywords.
                        </p>
                        <button
                            onClick=${() => { setQuery(''); setFilterType('ALL'); }}
                            class="mt-8 px-6 py-2.5 bg-brand-500 hover:bg-brand-600 text-white rounded-xl transition-all shadow-lg shadow-brand-500/30 font-medium focus-ring"
                        >
                            Clear Filters
                        </button>
                    </div>
                ` : html`
                    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6 animate-fade-in">
                        ${processedFiles.map(file => html`
                            <${ArtifactCard}
                                key=${file.filename}
                                file=${file}
                                onCopy=${handleCopy}
                            />
                        `)}
                    </div>
                `}
            </main>

            <${Footer} lastUpdated=${stats.lastUpdated} />

            ${toast && html`<${Toast} message=${toast.message} type=${toast.type} />`}
        </div>
    `;
};

render(html`<${App} />`, document.getElementById('app'));
