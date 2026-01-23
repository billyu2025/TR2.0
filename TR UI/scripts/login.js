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
    },
    methods: {
        async handleLogin() {
            this.errorMessage = '';
            this.successMessage = '';

            if (!this.loginForm.username || !this.loginForm.password) {
                this.errorMessage = '请输入账号名称和密码';
                return;
            }

            this.loading = true;
            try {
                // 获取 API 基础 URL，如果是相对路径（以 / 开头），直接使用；否则拼接 /api
                const apiBaseUrl = window.API_BASE_URL || 'http://127.0.0.1:5000';
                const apiUrl = apiBaseUrl.startsWith('/') 
                    ? `${apiBaseUrl}/auth/login`  // 相对路径，去掉 /api 前缀（因为 apiBaseUrl 已经是 /api）
                    : `${apiBaseUrl}/api/auth/login`;  // 绝对路径，需要加上 /api
                const response = await fetch(apiUrl, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username: this.loginForm.username.trim(),
                        password: this.loginForm.password
                    })
                });

                const result = await response.json();

                if (!response.ok || !result.success) {
                    throw new Error(result.error || '登录失败');
                }

                this.successMessage = `欢迎回来，${result.user.name || result.user.username}！`;
                this.persistAuthInfo(result);

                setTimeout(() => {
                    window.location.href = 'tr-records.html';
                }, 800);
            } catch (error) {
                console.error('登录失败:', error);
                this.errorMessage = error.message || '登录失败，请稍后重试';
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
                console.warn('无法读取记住的账号信息:', err);
            }
        }
    }
}).mount('#app');


