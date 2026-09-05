/**
 * DemoGen API Client
 * Handles communication with backend API
 */

const API_BASE = '/api';

class APIClient {
    constructor(baseURL = API_BASE) {
        this.baseURL = baseURL;
    }

    async request(endpoint, options = {}) {
        const url = `${this.baseURL}${endpoint}`;
        const defaultOptions = {
            headers: {
                'Content-Type': 'application/json',
            },
            ...options
        };

        const response = await fetch(url, defaultOptions);

        if (!response.ok) {
            // Surface the server's own message. Without this every failure
            // reached the UI as "API Error: 500 Internal Server Error", which
            // hid the actual pipeline error.
            let detail = '';
            try {
                const body = await response.json();
                detail = body.detail || body.error || body.message || '';
            } catch (_) {
                try { detail = (await response.text()).slice(0, 300); } catch (_) { /* ignore */ }
            }
            const err = new Error(detail || `${response.status} ${response.statusText}`);
            err.status = response.status;
            console.error(`API ${options.method || 'GET'} ${url} failed:`, err.message);
            throw err;
        }

        return response.json();
    }

    async get(endpoint) {
        return this.request(endpoint, { method: 'GET' });
    }

    async post(endpoint, data) {
        return this.request(endpoint, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    async put(endpoint, data) {
        return this.request(endpoint, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    }

    async delete(endpoint) {
        return this.request(endpoint, { method: 'DELETE' });
    }

    // DemoGen Specific Methods

    async health() {
        return this.get('/health');
    }

    async generateDemo(prompt, language = 'en', feature = null, targetUrl = null, useMockSite = null) {
        return this.post('/generate', {
            prompt,
            language,
            feature,
            // null lets the server decide via USE_MOCK_SITE_BY_DEFAULT.
            use_mock_site: useMockSite,
            target_url: targetUrl,
            allow_partial: true
        });
    }

    async listDemos() {
        return this.get('/demos');
    }

    async listLanguages() {
        return this.get('/languages');
    }

    async getVideo(videoId) {
        return this.get(`/videos/${videoId}`);
    }

    async validatePrompt(prompt, language = 'en') {
        return this.post('/validate-prompt', {
            prompt,
            language
        });
    }
}

// Create global API client instance
const api = new APIClient();
