import { html } from 'https://esm.sh/htm/preact';

export const Toast = ({ message, type = 'success' }) => html`
    <div class="fixed bottom-4 right-4 z-[9999] transition-all duration-300 transform animate-slide-up">
        <div class="glass dark:bg-gray-800 shadow-xl border-l-4 border-brand-500 rounded-lg p-4 flex items-center space-x-3 pr-6">
            <div class="${type === 'success' ? 'text-green-500' : 'text-blue-500'}">
                <i data-lucide="${type === 'success' ? 'check-circle-2' : 'info'}" class="w-5 h-5"></i>
            </div>
            <div>
                <p class="text-sm font-medium text-gray-900 dark:text-gray-100">${message}</p>
            </div>
        </div>
    </div>
`;

export const Hero = () => html`
    <div class="relative py-16 sm:py-24 text-center overflow-hidden">
        <!-- Abstract Decoration -->
        <div class="absolute inset-0 z-0 pointer-events-none opacity-30 dark:opacity-20 flex justify-center items-center">
            <div class="w-[600px] h-[600px] bg-brand-500/20 rounded-full blur-[100px] animate-pulse duration-[3000ms]"></div>
            <div class="absolute w-[400px] h-[400px] bg-indigo-500/20 rounded-full blur-[80px] translate-x-24 -translate-y-12"></div>
        </div>

        <div class="relative z-10 max-w-4xl mx-auto px-4">
            <div class="inline-flex items-center space-x-2 px-3 py-1 bg-brand-50 dark:bg-brand-900/30 border border-brand-200 dark:border-brand-800 rounded-full text-brand-700 dark:text-brand-300 text-xs font-semibold uppercase tracking-wider mb-6 animate-fade-in">
                <span class="w-2 h-2 rounded-full bg-brand-500 animate-pulse"></span>
                <span>Artifact Repository</span>
            </div>

            <h1 class="text-5xl sm:text-6xl font-bold tracking-tight text-gray-900 dark:text-white mb-6">
                Generated <span class="bg-clip-text text-transparent bg-gradient-to-r from-brand-500 via-sky-500 to-indigo-500">Proxy Configs</span>
            </h1>

            <p class="text-lg sm:text-xl text-gray-600 dark:text-gray-300 max-w-2xl mx-auto leading-relaxed">
                Automated aggregation and generation of high-quality proxy artifacts. <br class="hidden sm:block"/>
                Updated regularly for optimal connectivity.
            </p>
        </div>
    </div>
`;

export const Header = ({ onSearch, stats, theme, onToggleTheme }) => html`
    <header class="glass sticky top-0 z-50 transition-all duration-300 border-b border-gray-200/50 dark:border-gray-800/50">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-4">

            <!-- Logo -->
            <div class="flex items-center space-x-3 shrink-0 cursor-pointer group" onClick=${() => window.scrollTo({top: 0, behavior: 'smooth'})}>
                <div class="bg-gradient-to-br from-brand-500 to-indigo-600 text-white p-2 rounded-lg shadow-lg shadow-brand-500/20 group-hover:scale-105 transition-transform duration-200">
                    <i data-lucide="box" class="w-5 h-5"></i>
                </div>
                <span class="text-lg font-bold text-gray-900 dark:text-white tracking-tight">GatherX</span>
            </div>

            <!-- Search -->
            <div class="flex-1 max-w-lg w-full mx-4">
                <div class="relative group">
                    <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                        <i data-lucide="search" class="h-4 w-4 text-gray-400 group-focus-within:text-brand-500 transition-colors"></i>
                    </div>
                    <input
                        type="text"
                        class="block w-full pl-10 pr-10 py-2 bg-gray-100/50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700 rounded-xl text-sm placeholder-gray-500 text-gray-900 dark:text-gray-100 focus-ring transition-all"
                        placeholder="Search by name, protocol, or tag..."
                        onInput=${(e) => onSearch(e.target.value)}
                    />
                    <div class="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none">
                        <kbd class="hidden sm:inline-block px-2 py-0.5 bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded text-xs text-gray-400 font-sans">
                            /
                        </kbd>
                    </div>
                </div>
            </div>

            <!-- Actions -->
            <div class="flex items-center space-x-2 sm:space-x-4">
                <div class="hidden md:flex items-center space-x-4 text-xs font-medium text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-800/50 py-1.5 px-3 rounded-full border border-gray-200 dark:border-gray-700/50">
                    <span title="Total Files">${stats.totalFiles} files</span>
                    <span class="w-1 h-1 bg-gray-300 dark:bg-gray-600 rounded-full"></span>
                    <span title="Total Size">${stats.totalSize}</span>
                </div>

                <button
                    onClick=${onToggleTheme}
                    class="p-2 rounded-lg text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors focus-ring"
                    title="Toggle Theme"
                >
                    <i data-lucide="${theme === 'dark' ? 'sun' : 'moon'}" class="w-5 h-5"></i>
                </button>

                <a href="https://github.com/cyb3r-jak3/huntx" target="_blank" class="hidden sm:flex p-2 rounded-lg text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors focus-ring">
                    <i data-lucide="github" class="w-5 h-5"></i>
                </a>
            </div>
        </div>
    </header>
`;

export const ControlBar = ({ types, activeType, onSelectType, sortOption, onSortChange }) => html`
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-gray-100 dark:border-gray-800/50 pb-6 mb-6">

        <!-- Filter Tabs -->
        <div class="flex flex-wrap gap-2">
            <button
                class="px-4 py-1.5 rounded-full text-sm font-medium transition-all duration-200 focus-ring ${activeType === 'ALL' ? 'bg-brand-500 text-white shadow-md shadow-brand-500/25 ring-2 ring-brand-500 ring-offset-2 dark:ring-offset-gray-900' : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 border border-gray-200 dark:border-gray-700'}"
                onClick=${() => onSelectType('ALL')}
            >
                All
            </button>
            ${types.map(type => html`
                <button
                    class="px-4 py-1.5 rounded-full text-sm font-medium transition-all duration-200 focus-ring ${activeType === type ? 'bg-brand-500 text-white shadow-md shadow-brand-500/25 ring-2 ring-brand-500 ring-offset-2 dark:ring-offset-gray-900' : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 border border-gray-200 dark:border-gray-700'}"
                    onClick=${() => onSelectType(type)}
                >
                    ${type}
                </button>
            `)}
        </div>

        <!-- Sort Dropdown -->
        <div class="relative flex items-center space-x-2">
            <span class="text-xs text-gray-500 uppercase tracking-wider font-semibold">Sort by</span>
            <select
                class="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-200 text-sm rounded-lg focus:ring-brand-500 focus:border-brand-500 block w-full p-2 pl-3 pr-8 appearance-none cursor-pointer hover:border-brand-400 transition-colors"
                value=${sortOption}
                onChange=${(e) => onSortChange(e.target.value)}
            >
                <option value="date_desc">Newest First</option>
                <option value="date_asc">Oldest First</option>
                <option value="name_asc">Name (A-Z)</option>
                <option value="size_desc">Size (Large to Small)</option>
            </select>
            <div class="absolute right-2 pointer-events-none text-gray-400">
                <i data-lucide="chevron-down" class="w-4 h-4"></i>
            </div>
        </div>
    </div>
`;

export const ArtifactCard = ({ file, onCopy }) => {
    // Determine icon based on type
    let iconName = 'file-code';
    let colorClass = 'text-gray-500 bg-gray-100 dark:bg-gray-800';

    if (file.type === 'Subscription' || file.ext === 'B64SUB') {
        iconName = 'rss';
        colorClass = 'text-orange-500 bg-orange-50 dark:bg-orange-900/20';
    } else if (file.type === 'Config' || file.ext === 'CONF' || file.ext === 'YAML') {
        iconName = 'settings-2';
        colorClass = 'text-blue-500 bg-blue-50 dark:bg-blue-900/20';
    } else if (file.type === 'JSON') {
        iconName = 'braces';
        colorClass = 'text-yellow-500 bg-yellow-50 dark:bg-yellow-900/20';
    }

    return html`
    <div class="artifact-card group flex flex-col justify-between h-full rounded-2xl p-5 border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 shadow-sm transition-all duration-300 hover:shadow-xl hover:-translate-y-1">

        <!-- Header -->
        <div class="flex items-start justify-between mb-4">
            <div class="flex items-start space-x-4 overflow-hidden">
                <div class="shrink-0 p-3 rounded-xl ${colorClass} transition-colors">
                    <i data-lucide="${iconName}" class="w-6 h-6"></i>
                </div>
                <div class="min-w-0">
                    <h3 class="text-base font-bold text-gray-900 dark:text-gray-100 truncate pr-2" title="${file.filename}">
                        ${file.filename}
                    </h3>
                    <div class="flex flex-wrap items-center gap-2 mt-1.5">
                        <span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-gray-700">
                            ${file.ext}
                        </span>
                        <span class="text-xs text-gray-400 font-mono">${file.size_str}</span>
                    </div>
                </div>
            </div>
        </div>

        <!-- Tags -->
        <div class="flex flex-wrap gap-1.5 mb-6 min-h-[1.5rem]">
            ${file.tags && file.tags.slice(0, 4).map(tag => html`
                <span class="inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-medium bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300 border border-indigo-100 dark:border-indigo-800/50 uppercase tracking-wide">
                    ${tag}
                </span>
            `)}
            ${file.tags && file.tags.length > 4 ? html`
                <span class="inline-flex items-center px-1.5 py-0.5 rounded-md text-[10px] font-medium bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400">
                    +${file.tags.length - 4}
                </span>
            ` : ''}
        </div>

        <!-- Actions -->
        <div class="mt-auto pt-4 border-t border-gray-100 dark:border-gray-800 flex gap-3">
            <a
                href="${file.path}"
                download
                class="flex-1 flex items-center justify-center space-x-2 px-4 py-2.5 bg-gray-900 dark:bg-white hover:bg-gray-800 dark:hover:bg-gray-200 text-white dark:text-gray-900 text-sm font-semibold rounded-xl transition-all shadow-md hover:shadow-lg focus-ring"
            >
                <i data-lucide="download" class="w-4 h-4"></i>
                <span>Download</span>
            </a>
            <button
                onClick=${(e) => onCopy(file.path, e.currentTarget)}
                class="p-2.5 text-gray-500 hover:text-brand-600 dark:text-gray-400 dark:hover:text-brand-400 bg-gray-50 dark:bg-gray-800 hover:bg-brand-50 dark:hover:bg-brand-900/20 rounded-xl transition-all border border-gray-200 dark:border-gray-700 hover:border-brand-200 dark:hover:border-brand-800 focus-ring"
                title="Copy Link"
            >
                <i data-lucide="link" class="w-5 h-5"></i>
            </button>
        </div>
    </div>
    `;
};

export const Footer = ({ lastUpdated }) => html`
    <footer class="mt-auto border-t border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 py-10">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col md:flex-row justify-between items-center text-sm text-gray-500 dark:text-gray-400 gap-4">
            <div class="flex items-center space-x-2">
                <div class="w-2 h-2 rounded-full bg-green-500 animate-pulse"></div>
                <span>Last Updated: <span class="font-mono text-gray-700 dark:text-gray-300 font-medium">${lastUpdated}</span></span>
            </div>

            <div class="flex items-center space-x-6">
                <a href="#" class="hover:text-brand-500 transition-colors">Privacy</a>
                <a href="#" class="hover:text-brand-500 transition-colors">Terms</a>
                <a href="https://github.com/cyb3r-jak3/huntx" target="_blank" class="flex items-center space-x-1.5 text-gray-700 dark:text-gray-300 hover:text-brand-500 dark:hover:text-brand-400 transition-colors font-medium">
                    <i data-lucide="github" class="w-4 h-4"></i>
                    <span>GitHub</span>
                </a>
            </div>
        </div>
    </footer>
`;
