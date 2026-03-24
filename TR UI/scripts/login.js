const { createApp } = Vue;

createApp({
    data() {
        return {
            loginForm: {
                username: '',
                password: '',
                role: 'admin',
                remember: false
            },
            showPassword: false,
            errorMessage: '',
            successMessage: '',
            loading: false
        };
    },
    mounted() {
        this.restoreRememberedUser();
        sessionStorage.removeItem('authInfo');
        sessionStorage.removeItem('userSettings');
        this.ensureHttpAccess();
    },
    methods: {
        ensureHttpAccess() {
            if (window.location.protocol !== 'file:') return;

            const redirected = sessionStorage.getItem('loginRedirectTried') === '1';
            const targetUrl = 'http://localhost:8000/login.html';

            if (!redirected) {
                sessionStorage.setItem('loginRedirectTried', '1');
                window.location.href = targetUrl;
                return;
            }

            this.errorMessage = '請使用 HTTP 地址訪問： http://localhost:8000/login.html（不要直接雙擊打開 login.html）';
        },
        async handleLogin() {
            this.errorMessage = '';
            this.successMessage = '';

            if (window.location.protocol === 'file:') {
                this.errorMessage = '當前是 file:// 打開方式，瀏覽器會攔截登入請求。請改用 http://localhost:8000/login.html';
                return;
            }

            if (!this.loginForm.username || !this.loginForm.password) {
                this.errorMessage = '請輸入帳號名稱和密碼';
                return;
            }

            this.loading = true;
            try {
                // 统一规范 API URL，兼容: /api, /api/, http://host:5000, http://host:5000/api
                const apiBaseUrlRaw = (window.API_BASE_URL || 'http://127.0.0.1:5000').trim();
                const apiBaseUrl = apiBaseUrlRaw.replace(/\/+$/, '');
                const hasApiSuffix = /\/api$/i.test(apiBaseUrl);
                const apiUrl = `${apiBaseUrl}${hasApiSuffix ? '' : '/api'}/auth/login`;

                const response = await fetch(apiUrl, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username: this.loginForm.username.trim(),
                        password: this.loginForm.password
                    })
                });

                const responseText = await response.text();
                let result = {};
                try {
                    result = responseText ? JSON.parse(responseText) : {};
                } catch (parseError) {
                    throw new Error(`登入服務回應格式錯誤（HTTP ${response.status}）`);
                }

                if (!response.ok || !result.success) {
                    throw new Error(result.error || `登入失敗（HTTP ${response.status}）`);
                }

                this.successMessage = `歡迎回來，${result.user.name || result.user.username}！`;
                this.persistAuthInfo(result);

                setTimeout(() => {
                    window.location.href = 'tr-records.html';
                }, 800);
            } catch (error) {
                console.error('登入失敗:', error);
                this.errorMessage = error.message || '登入失敗，請稍後重試';
            } finally {
                this.loading = false;
            }
        },
        persistAuthInfo(result) {
            const authInfo = {
                token: result.token,
                expires_at: result.expires_at,
                user: result.user,
                login_time: new Date().toISOString()
            };
            sessionStorage.setItem('authInfo', JSON.stringify(authInfo));

            if (this.loginForm.remember) {
                localStorage.setItem('rememberedUser', JSON.stringify({
                    username: this.loginForm.username.trim(),
                    role: result.user.role
                }));
            } else {
                localStorage.removeItem('rememberedUser');
            }
        },
        restoreRememberedUser() {
            const remembered = localStorage.getItem('rememberedUser');
            if (!remembered) return;
            try {
                const parsed = JSON.parse(remembered);
                this.loginForm.username = parsed.username || '';
                this.loginForm.role = parsed.role || 'admin';
                this.loginForm.remember = true;
            } catch (err) {
                console.warn('無法讀取記住的帳號資訊:', err);
            }
        }
    }
}).mount('#app');


