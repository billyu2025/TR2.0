const { createApp } = Vue;

createApp({
    data() {
        return {
            userInfo: {
                username: '',
                name: '',
                role: '',
                loginTime: ''
            },
            activeMenu: 'dashboard',
            menuItems: []
        };
    },
    computed: {
        // 根据用户角色动态生成菜单
        dynamicMenuItems() {
            const baseMenu = [
                { id: 'dashboard', icon: '🏠', text: '控制台' },
                { id: 'reports', icon: '📊', text: '报告管理' },
                { id: 'data', icon: '📁', text: '数据管理' }
            ];

            if (this.userInfo.role === 'admin') {
                baseMenu.push(
                    { id: 'users', icon: '👥', text: '用户管理' },
                    { id: 'settings', icon: '⚙️', text: '系统设置' }
                );
            } else {
                baseMenu.push(
                    { id: 'profile', icon: '👤', text: '个人中心' }
                );
            }

            return baseMenu;
        }
    },
    mounted() {
        // 检查登录状态
        this.checkLoginStatus();
        // 设置菜单项
        this.menuItems = this.dynamicMenuItems;
    },
    methods: {
        checkLoginStatus() {
            // 从 sessionStorage 获取用户信息
            const userInfoStr = sessionStorage.getItem('userInfo');
            
            if (!userInfoStr) {
                // 如果没有登录信息，跳转到登录页面
                alert('請先登入！');
                window.location.href = 'login.html';
                return;
            }

            try {
                this.userInfo = JSON.parse(userInfoStr);
                console.log('当前登录用户:', this.userInfo);
            } catch (e) {
                console.error('解析用户信息失败:', e);
                window.location.href = 'login.html';
            }
        },

        handleLogout() {
            // 确认退出
            if (confirm('確定要退出登入嗎？')) {
                // 清除登录信息
                sessionStorage.removeItem('userInfo');
                
                // 跳转到登录页面
                window.location.href = 'login.html';
            }
        },

        goToPage(page) {
            window.location.href = `${page}.html`;
        }
    },
    watch: {
        // 监听用户信息变化，更新菜单
        'userInfo.role': function(newRole) {
            this.menuItems = this.dynamicMenuItems;
        }
    }
}).mount('#app');

// 页面加载完成后的初始化
document.addEventListener('DOMContentLoaded', () => {
    console.log('TR Report System 主控制台已加载');
});

