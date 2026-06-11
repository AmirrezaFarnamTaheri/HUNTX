import Fuse from 'https://esm.sh/fuse.js@7.0.0';

class ArtifactStore {
    constructor() {
        this.data = null;
        this.fuse = null;
        this.files = [];
        this.loading = true;
        this.error = null;
        this.CACHE_KEY = 'gatherx_catalog_cache';
        this.CACHE_TTL = 3600 * 1000; // 1 hour
    }

    async init() {
        try {
            // Check cache first
            const cached = localStorage.getItem(this.CACHE_KEY);
            if (cached) {
                try {
                    const { timestamp, data } = JSON.parse(cached);
                    const now = Date.now();
                    if (now - timestamp < this.CACHE_TTL) {
                        console.log('Using cached catalog data');
                        this._processData(data);

                        // Fetch in background to update if needed
                        this._fetchAndCache(true);
                        return;
                    }
                } catch (e) {
                    console.warn('Cache parsing failed', e);
                    localStorage.removeItem(this.CACHE_KEY);
                }
            }

            await this._fetchAndCache();
        } catch (err) {
            console.error('Store init error:', err);
            this.error = err.message;
            this.loading = false;
        }
    }

    async _fetchAndCache(isBackground = false) {
        try {
            const response = await fetch('./catalog.json', { cache: 'no-store' });
            if (!response.ok) throw new Error('Failed to load catalog');

            const data = await response.json();

            // Update cache
            try {
                localStorage.setItem(this.CACHE_KEY, JSON.stringify({
                    timestamp: Date.now(),
                    generated_at: data?.generated_at || null,
                    data: data
                }));
            } catch (e) {
                // QuotaExceededError is common for large catalogs; caching is best-effort only.
                console.warn('Cache write failed (quota?)', e);
            }

            const prevGenerated = this.data?.generated_at || null;
            const nextGenerated = data?.generated_at || null;

            if (!isBackground || (nextGenerated && nextGenerated !== prevGenerated) || !this.data) {
                this._processData(data);
            }
        } catch (err) {
            if (!isBackground) throw err;
        }
    }

    _processData(data) {
        this.data = data;
        this.files = this.data.files || [];

        // Initialize Fuse with enhanced keys
        const options = {
            keys: [
                { name: 'filename', weight: 0.7 },
                { name: 'tags', weight: 0.5 },
                { name: 'type', weight: 0.3 },
                { name: 'ext', weight: 0.2 }
            ],
            threshold: 0.3,
            distance: 100,
            ignoreLocation: true
        };
        this.fuse = new Fuse(this.files, options);
        this.loading = false;
    }

    search(query) {
        if (!query || !this.fuse) return this.files;
        return this.fuse.search(query).map(result => result.item);
    }

    filter(files, type) {
        if (!type || type === 'ALL') return files;
        return files.filter(file => file.type === type);
    }

    getStats() {
        if (!this.data) return { totalFiles: 0, totalSize: '0 B', lastUpdated: '-' };
        return {
            totalFiles: this.data.total_files,
            totalSize: this.data.total_size_str,
            lastUpdated: new Date(this.data.generated_at).toLocaleString()
        };
    }
}

export const store = new ArtifactStore();
