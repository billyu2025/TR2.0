// API 基础 URL，从配置文件读取
// 直接使用 window.API_BASE_URL，避免重复声明错误

const { createApp } = Vue;

function getAuthInfo() {
    try {
        return JSON.parse(sessionStorage.getItem('authInfo') || '{}');
    } catch (error) {
        return {};
    }
}

// 辅助函数：构建正确的 API URL，避免路径重复
function buildApiUrl(path) {
    const apiBaseUrl = window.API_BASE_URL || 'http://127.0.0.1:5000';
    // 如果 apiBaseUrl 是相对路径（以 / 开头），且 path 也以 /api 开头，则去掉 path 中的 /api 前缀
    let finalPath = path;
    if (apiBaseUrl.startsWith('/') && path.startsWith('/api/')) {
        finalPath = path.substring(4); // 去掉 '/api' 前缀，保留 '/auth/me' 等
    }
    return `${apiBaseUrl}${finalPath}`;
}

async function apiFetch(path, options = {}) {
    const authInfo = getAuthInfo();
    const headers = Object.assign({}, options.headers || {});
    if (authInfo.token) {
        headers['Authorization'] = `Bearer ${authInfo.token}`;
    }
    if (options.body && !headers['Content-Type']) {
        headers['Content-Type'] = 'application/json';
    }
    const response = await fetch(buildApiUrl(path), { ...options, headers });
    if (response.status === 401) {
        sessionStorage.removeItem('authInfo');
        sessionStorage.removeItem('userSettings');
        window.location.href = 'login.html';
        throw new Error('登录状态已过期，请重新登录');
    }
    const result = await response.json().catch(() => ({}));
    if (!response.ok || result.success === false) {
        throw new Error(result.error || `请求失败（${response.status}）`);
    }
    return result;
}

createApp({
    data() {
        return {
            loading: false,
            userInfo: {
                username: '',
                name: '',
                role: '',
                jobNos: []
            },
            showSettings: false,
            userSettings: {
                avatar: 'admin',
                name: '',
                email: '',
                phone: '',
                department: '',
                notes: ''
            },
            avatarOptions: [
                { value: 'admin', icon: '👑' },
                { value: 'default', icon: '👤' },
                { value: 'user', icon: '🧑' },
                { value: 'engineer', icon: '👩‍💻' },
                { value: 'staff', icon: '👨‍💻' }
            ],
            searchText: '',
            users: [],
            modal: {
                visible: false,
                mode: 'create',
                form: {
                    username: '',
                    password: '',
                    role: 'user',
                    jobNos: [''],
                    active: true
                }
            }
        };
    },
    computed: {
        filteredUsers() {
            if (!this.searchText.trim()) {
                return this.users;
            }
            const keyword = this.searchText.trim().toLowerCase();
            return this.users.filter(user => {
                const jobMatch = user.jobNos.some(job => job.toLowerCase().includes(keyword));
                return user.username.toLowerCase().includes(keyword) || jobMatch;
            });
        },
        activeUsers() {
            return this.users.filter(user => user.active).length;
        },
        totalJobCount() {
            return this.users.reduce((sum, user) => sum + user.jobNos.length, 0);
        }
    },
    async mounted() {
        try {
            await this.bootstrapUser();
            this.loadUserSettings();
            await this.fetchUsers();
        } catch (error) {
            console.error('初始化失败:', error);
            alert(error.message || '初始化失败，请重新登录');
            sessionStorage.removeItem('authInfo');
            window.location.href = 'login.html';
        }
    },
    methods: {
        async bootstrapUser() {
            const authInfo = getAuthInfo();
            if (!authInfo.token) {
                throw new Error('请先登录');
            }
            const profile = await apiFetch('/api/auth/me');
            const user = profile.user;
            if (user.role !== 'admin') {
                alert('只有管理账号可以访问账号管理页面！');
                window.location.href = 'tr-records.html';
                throw new Error('无权限');
            }
            this.userInfo = {
                username: user.username,
                name: user.name,
                role: user.role,
                jobNos: user.job_nos || []
            };
            sessionStorage.setItem('authInfo', JSON.stringify({
                token: authInfo.token,
                expires_at: authInfo.expires_at,
                user,
                login_time: authInfo.login_time
            }));
        },

        async fetchUsers() {
            this.loading = true;
            try {
                const result = await apiFetch('/api/admin/users');
                this.users = result.users.map(user => ({
                    username: user.username,
                    role: user.role,
                    active: user.active,
                    jobNos: user.job_nos || [],
                    createdAt: user.created_at,
                    updatedAt: user.updated_at
                }));
            } catch (error) {
                console.error('加载用户列表失败:', error);
                alert(error.message || '加载用户列表失败，请稍后重试');
            } finally {
                this.loading = false;
            }
        },

        getCurrentAvatar() {
            const selected = this.avatarOptions.find(item => item.value === this.userSettings.avatar);
            return selected ? selected.icon : '👑';
        },

        openCreateModal() {
            this.modal.mode = 'create';
            this.modal.form = {
                username: '',
                password: '',
                role: 'user',
                jobNos: [''],
                active: true
            };
            this.modal.visible = true;
        },

        openEditModal(user) {
            this.modal.mode = 'edit';
            this.modal.form = {
                username: user.username,
                password: '',
                role: user.role || 'user',
                jobNos: user.jobNos.length ? [...user.jobNos] : [''],
                active: user.active
            };
            this.modal.visible = true;
        },

        closeModal() {
            this.modal.visible = false;
        },

        parseJobNos(input) {
            if (!input) return [];
            return input
                .split(/[\n,，]+/)
                .map(item => item.trim())
                .filter(Boolean);
        },

        async submitModal() {
            const form = this.modal.form;
            if (!form.username.trim()) {
                alert('用户名不能为空');
                return;
            }
            if (this.modal.mode === 'create' && !form.password.trim()) {
                alert('请设置初始密码');
                return;
            }
            const jobNos = form.jobNos
                .map(job => job.trim())
                .filter(job => job.length > 0);
            if (jobNos.some(job => !/^\d+$/.test(job))) {
                alert('Job No 只能填写数字');
                return;
            }
            try {
                if (this.modal.mode === 'create') {
                    const payload = {
                        username: form.username.trim(),
                        password: form.password.trim(),
                        role: form.role || 'user',
                        active: form.active
                    };
                    // manager不需要Job No，user需要
                    if (form.role === 'user') {
                        payload.job_nos = jobNos;
                    }
                    await apiFetch('/api/admin/users', {
                        method: 'POST',
                        body: JSON.stringify(payload)
                    });
                    const roleName = form.role === 'manager' ? '管理账号' : '普通账号';
                    alert(`已创建${roleName}`);
                } else {
                    const payload = {
                        active: form.active
                    };
                    if (form.password && form.password.trim()) {
                        payload.password = form.password.trim();
                    }
                    // 只有user角色需要Job No
                    if (form.role === 'user') {
                        payload.job_nos = jobNos;
                    }
                    await apiFetch(`/api/admin/users/${encodeURIComponent(form.username)}`, {
                        method: 'PUT',
                        body: JSON.stringify(payload)
                    });
                    alert('账号信息已更新');
                }
                this.modal.visible = false;
                await this.fetchUsers();
            } catch (error) {
                console.error('保存用户信息失败:', error);
                console.error('错误详情:', error.stack);
                const errorMsg = error.message || '保存用户信息失败';
                alert(`保存用户信息失败: ${errorMsg}\n\n请检查：\n1. 后端服务器是否运行（http://127.0.0.1:5000）\n2. 浏览器控制台是否有更多错误信息`);
            }
        },

        async toggleStatus(user) {
            try {
                await apiFetch(`/api/admin/users/${encodeURIComponent(user.username)}`, {
                    method: 'PUT',
                    body: JSON.stringify({ active: !user.active })
                });
                user.active = !user.active;
            } catch (error) {
                console.error('更新状态失败:', error);
                alert(error.message || '更新状态失败');
            }
        },

        getRoleName(role) {
            const roleMap = {
                'admin': '超级管理员',
                'manager': '管理账号',
                'user': '普通用户'
            };
            return roleMap[role] || role;
        },
        
        async deleteUser(user) {
            if (!confirm(`确定要删除用户 ${user.username} 吗？`)) {
                return;
            }
            try {
                await apiFetch(`/api/admin/users/${encodeURIComponent(user.username)}`, {
                    method: 'DELETE'
                });
                this.users = this.users.filter(item => item.username !== user.username);
                alert('用户已删除');
            } catch (error) {
                console.error('删除用户失败:', error);
                alert(error.message || '删除用户失败');
            }
        },

        async resetPassword(user) {
            const newPassword = prompt(`请输入 ${user.username} 的新密码`);
            if (!newPassword || !newPassword.trim()) {
                return;
            }
            try {
                await apiFetch(`/api/admin/users/${encodeURIComponent(user.username)}`, {
                    method: 'PUT',
                    body: JSON.stringify({ password: newPassword.trim() })
                });
                alert('密码已更新');
            } catch (error) {
                console.error('重置密码失败:', error);
                alert(error.message || '重置密码失败');
            }
        },

        addJobRow() {
            this.modal.form.jobNos.push('');
        },

        removeJobRow(index) {
            if (this.modal.form.jobNos.length === 1) return;
            this.modal.form.jobNos.splice(index, 1);
        },

        goToPage(page) {
            window.location.href = `${page}.html`;
        },

        async handleLogout() {
            try {
                await apiFetch('/api/auth/logout', { method: 'POST' });
            } catch (error) {
                console.warn('注销失败:', error);
            } finally {
                sessionStorage.removeItem('authInfo');
                sessionStorage.removeItem('userSettings');
                window.location.href = 'login.html';
            }
        },

        closeSettings() {
            this.showSettings = false;
        },

        loadUserSettings() {
            const savedSettings = sessionStorage.getItem('userSettings');
            if (savedSettings) {
                try {
                    this.userSettings = JSON.parse(savedSettings);
                } catch (error) {
                    console.error('解析用户设置失败:', error);
                }
            } else {
                this.userSettings = {
                    avatar: 'admin',
                    name: this.userInfo.name,
                    email: '',
                    phone: '',
                    department: '',
                    notes: ''
                };
            }
        },

        saveSettings() {
            if (!this.userSettings.name) {
                alert('用户名为必填项！');
                return;
            }
            sessionStorage.setItem('userSettings', JSON.stringify(this.userSettings));
            alert('设置已保存！');
            this.closeSettings();
        }
    }
}).mount('#app');


