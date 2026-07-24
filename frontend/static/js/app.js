/**
 * DemoGen Frontend Application
 * Handles UI interactions and state management
 */

class DemoGenApp {
    constructor() {
        this.currentSession = null;
        this.templates = [];
        this.history = [];
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.loadTemplates();
        this.loadHistory();
        this.checkAPI();
    }

    setupEventListeners() {
        // Tab switching
        document.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', () => this.switchTab(item.dataset.tab));
        });

        // Form submission
        const demoForm = document.getElementById('demoForm');
        if (demoForm) {
            demoForm.addEventListener('submit', (e) => this.handleGenerateSubmit(e));
        }
    }

    switchTab(tabName) {
        // Update navigation
        document.querySelectorAll('.nav-item').forEach(item => {
            item.classList.remove('active');
        });
        document.querySelector(`[data-tab="${tabName}"]`)?.classList.add('active');

        // Update content
        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.remove('active');
        });
        document.getElementById(tabName)?.classList.add('active');
    }

    async handleGenerateSubmit(e) {
        e.preventDefault();

        const prompt = document.getElementById('prompt').value;
        const language = document.getElementById('language').value;
        const feature = document.getElementById('feature').value;
        const targetUrl = document.getElementById('targetUrl').value.trim();

        if (!targetUrl) {
            alert('Please enter a target website URL');
            return;
        }

        if (!/^https?:\/\//i.test(targetUrl)) {
            alert('Target URL must start with http:// or https://');
            return;
        }

        if (!prompt.trim()) {
            alert('Please enter a prompt');
            return;
        }

        // Validate prompt
        try {
            const validation = await api.validatePrompt(prompt, language);
            if (!validation.valid) {
                alert(`Invalid prompt: ${validation.message}`);
                return;
            }
        } catch (error) {
            console.error('Validation error:', error);
            // Continue anyway
        }

        // Show status container
        const statusContainer = document.getElementById('statusContainer');
        statusContainer.style.display = 'block';

        // Hide result container
        document.getElementById('resultContainer').style.display = 'none';

        // Start generation
        this.startGeneration(prompt, language, feature, targetUrl);
    }

    async startGeneration(prompt, language, feature, targetUrl) {
        try {
            // Progress animation while the (blocking) generate request runs
            this.simulateProgress();

            const result = await api.generateDemo(prompt, language, feature, targetUrl);
            this.currentSession = result;

            // API already finished — show result immediately (partial still has video_url)
            this.showResult(result);
        } catch (error) {
            console.error('Generation error:', error);
            alert('Error generating demo: ' + error.message);
            document.getElementById('statusContainer').style.display = 'none';
        }
    }

    simulateProgress() {
        const progressFill = document.getElementById('progressFill');
        const progressText = document.getElementById('progressText');
        const steps = [
            { progress: 25, text: 'Running automation...' },
            { progress: 50, text: 'Generating narration...' },
            { progress: 75, text: 'Composing video...' },
            { progress: 95, text: 'Validating quality...' },
            { progress: 100, text: 'Complete!' }
        ];

        let stepIndex = 0;
        const interval = setInterval(() => {
            if (stepIndex < steps.length) {
                const step = steps[stepIndex];
                progressFill.style.width = step.progress + '%';
                progressText.textContent = step.text;
                stepIndex++;
            } else {
                clearInterval(interval);
            }
        }, 1000);
    }

    showResult(result) {
        document.getElementById('statusContainer').style.display = 'none';
        const resultContainer = document.getElementById('resultContainer');
        resultContainer.style.display = 'block';

        // Update video preview (cache-bust so fresh recordings load)
        if (result.video_url) {
            const videoSource = document.getElementById('videoSource');
            const sep = result.video_url.includes('?') ? '&' : '?';
            videoSource.src = `${result.video_url}${sep}t=${Date.now()}`;
            document.getElementById('videoPreview').load();
        } else {
            alert(result.message || 'Generation finished but no video file was produced.');
        }

        // Update metadata
        const durationEl = document.getElementById('videoDuration');
        if (durationEl) {
            durationEl.textContent = result.duration
                ? `${Number(result.duration).toFixed(1)}s`
                : (result.status || 'ready');
        }
        const qualityEl = document.getElementById('qualityScore');
        if (qualityEl) {
            if (typeof result.quality_score === 'number') {
                qualityEl.textContent = `${result.quality_score.toFixed(0)}/100`;
            } else if (result.status === 'partial') {
                qualityEl.textContent = 'Partial';
            } else {
                qualityEl.textContent = 'N/A';
            }
        }

        // Save to history
        this.addToHistory(result);
    }

    async loadTemplates() {
        try {
            const data = await api.listDemos();
            this.templates = data.demos || [];
            this.renderTemplates();
        } catch (error) {
            console.error('Failed to load templates:', error);
        }
    }

    renderTemplates() {
        const templatesGrid = document.getElementById('templatesGrid');
        if (!templatesGrid) return;

        templatesGrid.innerHTML = this.templates.map(demo => `
            <div class="template-card" onclick="app.selectTemplate('${demo.id}')">
                <div class="template-icon">🎬</div>
                <h4>${demo.name}</h4>
                <p>${demo.description}</p>
            </div>
        `).join('');
    }

    selectTemplate(id) {
        const template = this.templates.find(t => t.id === id);
        if (template) {
            document.getElementById('prompt').value = template.description;
            this.switchTab('generator');
        }
    }

    addToHistory(demo) {
        const now = new Date().toLocaleString();
        this.history.unshift({
            id: demo.session_id || Date.now(),
            prompt: demo.prompt || 'Demo',
            timestamp: now,
            duration: demo.duration || '--',
            url: demo.video_url
        });

        // Keep only last 10
        this.history = this.history.slice(0, 10);

        // Save to localStorage
        localStorage.setItem('demoHistory', JSON.stringify(this.history));

        this.renderHistory();
    }

    async loadHistory() {
        const saved = localStorage.getItem('demoHistory');
        if (saved) {
            this.history = JSON.parse(saved);
            this.renderHistory();
        }
    }

    renderHistory() {
        const historyList = document.getElementById('historyList');
        if (!historyList) return;

        if (this.history.length === 0) {
            historyList.innerHTML = '<p style="color: #888;">No history yet. Generate your first demo!</p>';
            return;
        }

        historyList.innerHTML = this.history.map(item => `
            <div class="history-item">
                <div class="history-content">
                    <h4>${item.prompt.substring(0, 50)}...</h4>
                    <p class="history-meta">${item.timestamp}</p>
                </div>
                <div class="history-actions">
                    <button class="play-btn" onclick="app.playVideo('${item.id}')">▶ Play</button>
                    <button class="delete-btn" onclick="app.deleteHistory('${item.id}')">✕</button>
                </div>
            </div>
        `).join('');
    }

    playVideo(id) {
        const item = this.history.find(h => h.id == id);
        if (item && item.url) {
            document.getElementById('videoSource').src = item.url;
            document.getElementById('videoPreview').load();
            this.switchTab('generator');
        }
    }

    deleteHistory(id) {
        if (confirm('Delete this demo from history?')) {
            this.history = this.history.filter(h => h.id != id);
            localStorage.setItem('demoHistory', JSON.stringify(this.history));
            this.renderHistory();
        }
    }

    async checkAPI() {
        try {
            const health = await api.health();
            console.log('API Status:', health);
        } catch (error) {
            console.warn('API not available:', error);
        }
    }
}

// Helper functions for button onclick handlers
function downloadVideo() {
    // Get the session ID from the current app state
    if (!window.app || !window.app.currentSession) {
        alert('No video selected. Please generate a demo first.');
        return;
    }
    
    const sessionId = window.app.currentSession.session_id;
    if (!sessionId) {
        alert('Unable to download: session ID not found');
        return;
    }
    
    // Download via API endpoint
    const downloadUrl = `/api/download/${sessionId}`;
    const a = document.createElement('a');
    a.href = downloadUrl;
    a.download = `demo_${sessionId}.mp4`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

function shareVideo() {
    alert('Share functionality coming soon!');
}

function regenerateDemo() {
    window.app.switchTab('generator');
    document.getElementById('prompt').focus();
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.app = new DemoGenApp();
});
