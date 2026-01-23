const { createApp } = Vue;

createApp({
    data() {
        return {
            API_BASE_URL: 'http://localhost:5000',
            userInfo: {
                username: '',
                name: '',
                role: ''
            },
            activeTab: 'overview',
            loading: false,
            orders: [],
            filteredOrders: [],
            filters: {
                orderNo: '',
                jobNo: '',
                status: ''
            },
            currentPage: 1,
            pageSize: 12,
            dashboard: {
                totalOrders: 0,
                generated: 0,
                pending: 0,
                generatedRate: 0,
                latestGenerated: ''
            },
            systemStatus: {
                database: true,
                scheduler: '正常',
                mail: '未启用'
            },
            jobSummary: [],
            userAccounts: [
                { username: 'superadmin', name: '系统管理员', role: 'admin', jobNos: [], active: true },
                { username: 'henry', name: 'Henry Yu', role: 'manager', jobNos: ['TR-1269', 'TR-1270'], active: true },
                { username: 'operator01', name: '现场操作员A', role: 'user', jobNos: ['TR-1270'], active: true },
                { username: 'viewer02', name: '资料员B', role: 'user', jobNos: [], active: false }
            ],
            systemTasks: [
                { id: 1, name: '每日数据更新', schedule: '每天 06:30', description: '同步 Orders 与 Materials，刷新 Orders_gen_pdf', statusText: '下一次运行：明日 06:30', statusClass: 'tag--pending' },
                { id: 2, name: 'PDF 生成状态巡检', schedule: '每小时', description: '检查 PDF_Status 表，统计失败记录并发送提醒', statusText: '上一次成功：09:00', statusClass: 'tag--generated' },
                { id: 3, name: '日志归档', schedule: '每周一 00:30', description: '压缩 logs 目录，归档任务执行记录', statusText: '即将执行', statusClass: 'tag--pending' }
            ],
            activityLogs: [
                { id: 1, icon: '📄', title: 'TR_127712 PDF 已生成', detail: '由 auto_update_all_tables.py 于 2025-11-10 06:35 自动生成', time: '2小时前' },
                { id: 2, icon: '🔁', title: '自动任务运行完成', detail: '全量数据同步成功，更新 orders / materials / Orders_gen_pdf', time: '3小时前' },
                { id: 3, icon: '👤', title: '新账号创建：operator02', detail: '账号管理员 Henry 添加了新普通用户并分配 Job TR-1271', time: '昨天' }
            ],
            modal: {
                visible: false,
                mode: 'create',
                form: {
                    username: '',
                    name: '',
                    role: 'user',
                    jobNos: '',
                    password: ''
                }
            },
            _filterDebounce: null
        };
    },
    computed: {
        totalPages() {
            return Math.max(1, Math.ceil(this.filteredOrders.length / this.pageSize));
        },
        paginatedOrders() {
            const start = (this.currentPage - 1) * this.pageSize;
            return this.filteredOrders.slice(start, start + this.pageSize);
        }
    },
    watch: {
        currentPage(value) {
            if (value < 1) this.currentPage = 1;
            if (value > this.totalPages) this.currentPage = this.totalPages;
        },
        activeTab(newValue) {
            if (newValue === 'jobs' && this.jobSummary.length === 0) {
                this.buildJobSummary();
            }
        }
    },
    mounted() {
        this.checkLoginStatus();
        this.loadOrders();
        this.fetchSystemStatus();
    },
    methods: {
        checkLoginStatus() {
            const userInfoStr = sessionStorage.getItem('userInfo');
            if (!userInfoStr) {
                alert('请先登录！');
                window.location.href = 'login.html';
                return;
            }
            try {
                this.userInfo = JSON.parse(userInfoStr);
                if (this.userInfo.role !== 'admin') {
                    alert('当前页面仅限超级管理员访问！');
                    window.location.href = 'dashboard.html';
                }
            } catch (error) {
                console.error('解析用户信息失败:', error);
                window.location.href = 'login.html';
            }
        },
        async loadOrders() {
            this.loading = true;
            try {
                const response = await fetch(`${this.API_BASE_URL}/api/orders/list?page=1&per_page=all`);
                const result = await response.json();
                if (response.ok && result.success) {
                    this.orders = result.data.map(order => ({
                        orderNo: order.Order_No?.toString() ?? '',
                        jobNo: order.Job_No?.toString() ?? '',
                        client: order.Client ?? '',
                        jobsite: order.Jobsite ?? '',
                        delDate: order.Del_Date ?? '',
                        wt: Number(order.Wt) || 0,
                        status: (order.pdf_status || 'pending').toLowerCase(),
                        pdfPath: order.pdf_path ?? null,
                        generatedAt: order.generated_at ?? null
                    }));
                    this.filteredOrders = [...this.orders];
                    this.computeDashboard();
                    this.buildJobSummary();
                    this.currentPage = 1;
                } else {
                    console.error('加载订单失败:', result.error || response.statusText);
                }
            } catch (error) {
                console.error('订单接口异常:', error);
            } finally {
                this.loading = false;
            }
        },
        computeDashboard() {
            const total = this.orders.length;
            const generatedOrders = this.orders.filter(o => o.status === 'generated');
            const pendingOrders = this.orders.filter(o => o.status === 'pending');
            const latestGenerated = generatedOrders
                .map(o => o.generatedAt)
                .filter(Boolean)
                .sort()
                .reverse()[0] || '';

            this.dashboard.totalOrders = total;
            this.dashboard.generated = generatedOrders.length;
            this.dashboard.pending = pendingOrders.length;
            this.dashboard.generatedRate = total ? ((generatedOrders.length / total) * 100).toFixed(1) : 0;
            this.dashboard.latestGenerated = latestGenerated ? latestGenerated.replace('T', ' ') : '';
        },
        buildJobSummary() {
            const jobMap = new Map();
            this.orders.forEach(order => {
                const key = order.jobNo || '未指定';
                if (!jobMap.has(key)) {
                    jobMap.set(key, {
                        jobNo: key,
                        count: 0,
                        totalWt: 0,
                        generated: 0,
                        pending: 0
                    });
                }
                const summary = jobMap.get(key);
                summary.count += 1;
                summary.totalWt += order.wt || 0;
                if (order.status === 'generated') {
                    summary.generated += 1;
                } else if (order.status === 'pending') {
                    summary.pending += 1;
                }
            });
            this.jobSummary = Array.from(jobMap.values()).map(item => ({
                ...item,
                status: item.generated === item.count ? 'generated'
                    : item.pending === item.count ? 'pending'
                    : 'half'
            }));
        },
        renderStatus(status) {
            switch (status) {
                case 'generated':
                    return '已生成';
                case 'pending':
                    return '待生成';
                case 'failed':
                    return '失败';
                case 'half':
                    return '部分生成';
                default:
                    return status || '未知';
            }
        },
        renderRole(role) {
            switch (role) {
                case 'admin':
                    return '超级管理员';
                case 'manager':
                    return '账号管理员';
                case 'user':
                    return '普通用户';
                default:
                    return role;
            }
        },
        debouncedFilter() {
            if (this._filterDebounce) {
                clearTimeout(this._filterDebounce);
            }
            this._filterDebounce = setTimeout(() => {
                this.applyFilters();
            }, 250);
        },
        applyFilters() {
            const orderNoKeyword = this.filters.orderNo.trim().toLowerCase();
            const jobNoKeyword = this.filters.jobNo.trim().toLowerCase();
            const status = this.filters.status;

            this.filteredOrders = this.orders.filter(order => {
                const matchOrderNo = orderNoKeyword ? order.orderNo.toLowerCase().includes(orderNoKeyword) : true;
                const matchJobNo = jobNoKeyword ? order.jobNo.toLowerCase().includes(jobNoKeyword) : true;
                const matchStatus = status ? order.status === status : true;
                return matchOrderNo && matchJobNo && matchStatus;
            });

            this.currentPage = 1;
        },
        resetFilters() {
            this.filters.orderNo = '';
            this.filters.jobNo = '';
            this.filters.status = '';
            this.filteredOrders = [...this.orders];
            this.currentPage = 1;
        },
        openOrder(orderNo) {
            window.open(`tr-records.html#order=${orderNo}`, '_blank');
        },
        downloadPdf(order) {
            if (order.status !== 'generated') {
                alert('该订单尚未生成 PDF');
                return;
            }
            window.open(`${this.API_BASE_URL}/api/pdf/download/${order.orderNo}`, '_blank');
        },
        assignJob(jobNo) {
            alert(`未来将在此分配 Job ${jobNo} 的负责账号。`);
        },
        openCreateUser() {
            this.modal.mode = 'create';
            this.modal.form = {
                username: '',
                name: '',
                role: 'user',
                jobNos: '',
                password: ''
            };
            this.modal.visible = true;
        },
        editUser(user) {
            this.modal.mode = 'edit';
            this.modal.form = {
                username: user.username,
                name: user.name,
                role: user.role,
                jobNos: user.jobNos.join(', '),
                password: ''
            };
            this.modal.visible = true;
        },
        toggleUser(user) {
            user.active = !user.active;
        },
        resetPassword(user) {
            alert(`未来可在此发送重置密码邮件：${user.username}`);
        },
        closeModal() {
            this.modal.visible = false;
        },
        saveModalForm() {
            if (!this.modal.form.username || !this.modal.form.name) {
                alert('请填写完整信息');
                return;
            }
            if (this.modal.mode === 'create') {
                this.userAccounts.push({
                    username: this.modal.form.username,
                    name: this.modal.form.name,
                    role: this.modal.form.role,
                    jobNos: this.modal.form.jobNos
                        ? this.modal.form.jobNos.split(',').map(item => item.trim()).filter(Boolean)
                        : [],
                    active: true
                });
            } else {
                const target = this.userAccounts.find(u => u.username === this.modal.form.username);
                if (target) {
                    target.name = this.modal.form.name;
                    target.role = this.modal.form.role;
                    target.jobNos = this.modal.form.jobNos
                        ? this.modal.form.jobNos.split(',').map(item => item.trim()).filter(Boolean)
                        : [];
                }
            }
            this.modal.visible = false;
        },
        openPage(path) {
            window.location.href = path;
        },
        handleLogout() {
            sessionStorage.removeItem('userInfo');
            sessionStorage.removeItem('userSettings');
            window.location.href = 'login.html';
        },
        async fetchSystemStatus() {
            // 预留：后续可以请求真实的健康检查/任务状态，目前使用示例值
            try {
                const response = await fetch(`${this.API_BASE_URL}/health`);
                if (response.ok) {
                    const data = await response.json();
                    if (data?.status === 'ok') {
                        this.systemStatus.database = true;
                        this.systemStatus.scheduler = '正常';
                    }
                }
            } catch (error) {
                console.warn('健康检查接口不可用，使用默认状态');
                this.systemStatus.database = false;
                this.systemStatus.scheduler = '待检查';
            }
        }
    }
}).mount('#app');

