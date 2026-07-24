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

        try {
            const response = await fetch(url, defaultOptions);
            
            if (!response.ok) {
                throw new Error(`API Error: ${response.status} ${response.statusText}`);
            }

            return await response.json();
        } catch (error) {
            console.error('API Request failed:', error);
            throw error;
        }
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

    async generateDemo(prompt, language = 'en', feature = null, targetUrl = null) {
        return this.post('/generate', {
            prompt,
            language,
            feature,
            use_mock_site: false,
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

    async getSessions() {
        return this.get('/sessions');
    }

    async getSession(sessionId) {
        return this.get(`/session/${sessionId}`);
    }

    async getSessionScript(sessionId) {
        return this.get(`/session/${sessionId}/script`);
    }
}

// Create global API client instance
const api = new APIClient();
