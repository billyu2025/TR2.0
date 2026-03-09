// API 基礎 URL，從配置文件讀取
// 直接使用 window.API_BASE_URL，避免重复声明错误

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

// 带超时的 fetch 包装函数
async function fetchWithTimeout(url, options = {}, timeout = 300000) { // 5分钟超时
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);
    
    try {
        // 合并 signal（如果已有 AbortController）
        const mergedOptions = { ...options };
        if (options.signal) {
            // 如果已有 signal，创建一个组合的 AbortController
            const combinedController = new AbortController();
            options.signal.addEventListener('abort', () => combinedController.abort());
            controller.signal.addEventListener('abort', () => combinedController.abort());
            mergedOptions.signal = combinedController.signal;
        } else {
            mergedOptions.signal = controller.signal;
        }
        
        const response = await fetch(url, mergedOptions);
        clearTimeout(timeoutId);
        return response;
    } catch (error) {
        clearTimeout(timeoutId);
        if (error.name === 'AbortError' && !options.signal?.aborted) {
            throw new Error('请求超时，请检查网络连接');
        }
        throw error;
    }
}

// 带重试的 fetch 包装函数
async function fetchWithRetry(url, options = {}, maxRetries = 3, retryDelay = 1000) {
    let lastError;
    for (let i = 0; i < maxRetries; i++) {
        try {
            return await fetchWithTimeout(url, options);
        } catch (error) {
            lastError = error;
            // 如果是用户取消，不重试
            if (error.name === 'AbortError' && options.signal?.aborted) {
                throw error;
            }
            if (i < maxRetries - 1) {
                console.log(`[重试] 请求失败，${retryDelay}ms 后重试 (${i + 1}/${maxRetries})...`, error.message);
                await new Promise(resolve => setTimeout(resolve, retryDelay));
                retryDelay *= 2; // 指数退避
            }
        }
    }
    throw lastError;
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
    
    // 使用带超时和重试的 fetch
    const response = await fetchWithRetry(
        buildApiUrl(path), 
        { ...options, headers },
        300000, // 5分钟超时
        3,      // 最多重试3次
        2000    // 初始重试延迟2秒
    );
    
    const result = await response.json().catch(() => ({}));
    if (response.status === 401) {
        sessionStorage.removeItem('authInfo');
        sessionStorage.removeItem('userSettings');
        window.location.href = 'login.html';
        throw new Error(`${result.error || '登录状态已失效'}，请重新登录`);
    }
    if (!response.ok || result.success === false) {
        throw new Error(result.error || `请求失败（${response.status}）`);
    }
    return result;
}

async function buildHttpError(response, fallbackPrefix = '请求失败') {
    let errorMessage = `${fallbackPrefix}（HTTP ${response.status}）`;
    try {
        const result = await response.json();
        if (result && result.error) {
            errorMessage = result.error;
        }
    } catch (e) {
        // Keep fallback message when response is not JSON
    }

    if (response.status === 401) {
        sessionStorage.removeItem('authInfo');
        sessionStorage.removeItem('userSettings');
        window.location.href = 'login.html';
        return new Error(`${errorMessage}，请重新登录`);
    }
    return new Error(errorMessage);
}

const { createApp } = Vue;

createApp({
    data() {
        return {
            loading: false,
            activeSubTab: 'records', // 当前激活的子Tab：'records' 或 'stocklist-test'
            userInfo: {
                username: '',
                name: '',
                role: '',
                jobNos: []
            },
            defaultPageSize: 100,
            showSettings: false,
            userSettings: {
                avatar: 'default',
                name: '',
                email: '',
                phone: '',
                department: '',
                notes: ''
            },
            avatarOptions: [
                { value: 'default', icon: '👤' },
                { value: 'admin', icon: '👑' },
                { value: 'user', icon: '🧑' },
                { value: 'engineer', icon: '👩‍💻' },
                { value: 'staff', icon: '👨‍💻' }
            ],
            searchQuery: {
                orderNo: '',
                jobNo: '',
                dnNo: '',
                startDate: '',
                endDate: ''
            },
            records: [],
            filteredRecords: [],
            currentPage: 1,
            pageSize: 100,
            totalPagesComputed: 1,
            selectedRecords: {
                records: [],      // TR记录管理Tab的选择
                stocklistTest: [] // Stocklist&Test Report Tab的选择
            },
            isSearching: false,
            _searchDebounce: null,
            editModalVisible: false,
            editData: { header: {}, lines: [] },
            _editOriginal: null,
            isCancelling: false,
            currentAbortController: null,
            // 更新数据相关
            updateDataLoading: false,
            showUpdateModal: false,
            updateDataStatus: 'running', // 'running', 'completed', 'failed'
            updateDataMessage: '',
            updateCheckInterval: null,
            downloadProgressVisible: false
        };
    },
    computed: {
        minDate() {
            // 最早日期：3年前
            const date = new Date();
            date.setFullYear(date.getFullYear() - 3);
            return date.toISOString().split('T')[0];
        },
        maxDate() {
            // 最晚日期：今天
            return new Date().toISOString().split('T')[0];
        },
        totalPages() {
            return this.totalPagesComputed;
        },
        // 获取当前Tab的selectedRecords数组（只读）
        currentSelectedRecords() {
            return this.activeSubTab === 'records' 
                ? this.selectedRecords.records 
                : this.selectedRecords.stocklistTest;
        },
        // 用于v-model绑定的计算属性（带getter和setter）
        currentSelectedRecordsModel: {
            get() {
                return this.activeSubTab === 'records' 
                    ? this.selectedRecords.records 
                    : this.selectedRecords.stocklistTest;
            },
            set(value) {
                if (this.activeSubTab === 'records') {
                    this.selectedRecords.records = value;
                } else {
                    this.selectedRecords.stocklistTest = value;
                }
            }
        },
        isAllSelected() {
            const currentSelected = this.currentSelectedRecords;
            return this.filteredRecords.length > 0 && 
                   this.filteredRecords.every(record => currentSelected.includes(record.id));
        },
        selectedGeneratedCount() {
            const currentSelected = this.currentSelectedRecords;
            return currentSelected.filter(id => {
                const record = this.records.find(r => r.id === id);
                return record && record.status === 'generated';
            }).length;
        },
        hasSelectedGeneratedRecords() {
            return this.selectedGeneratedCount > 0;
        },
        selectedPendingCount() {
            const currentSelected = this.currentSelectedRecords;
            return currentSelected.filter(id => {
                const record = this.records.find(r => r.id === id);
                return record && record.status !== 'generated';
            }).length;
        },
        hasSelectedPendingRecords() {
            return this.selectedPendingCount > 0;
        }
    },
    watch: {
        // 监听标签页切换，自动重新加载数据
        activeSubTab(newTab, oldTab) {
            if (newTab !== oldTab) {
                console.log(`[前端] 标签页切换: ${oldTab} -> ${newTab}`);
                // 重置搜索状态和分页
                this.currentPage = 1;
                this.isSearching = false;
                this.searchQuery = { orderNo: '', jobNo: '', dnNo: '', startDate: '', endDate: '' };
                // 重新加载数据
                this.loadOrdersFromAPI(1);
            }
        }
    },
    async mounted() {
        // 页面重新进入时，先清理可能残留的更新状态和轮询
        if (this.updateCheckInterval) {
            clearInterval(this.updateCheckInterval);
            this.updateCheckInterval = null;
        }
        this.updateDataLoading = false;
        this.showUpdateModal = false;
        this.updateDataStatus = 'running';
        this.updateDataMessage = '';

        // 添加全局错误处理
        window.addEventListener('error', (event) => {
            console.error('[全局错误]', event.error);
            // 如果是下载相关的错误，显示友好提示
            if (event.error && event.error.message && 
                (event.error.message.includes('下载') || 
                 event.error.message.includes('网络') || 
                 event.error.message.includes('超时'))) {
                // 不在这里显示 alert，避免重复提示
                console.error('下载相关错误:', event.error.message);
            }
        });

        // 未处理的 Promise 拒绝
        window.addEventListener('unhandledrejection', (event) => {
            console.error('[未处理的 Promise 拒绝]', event.reason);
            if (event.reason && event.reason.message && 
                (event.reason.message.includes('下载') || 
                 event.reason.message.includes('网络') || 
                 event.reason.message.includes('超时'))) {
                console.error('下载相关错误:', event.reason.message);
            }
        });

        // 确保默认显示 TR记录管理，不显示设置弹窗
        this.activeSubTab = 'records';
        this.showSettings = false;
        
        // 添加Enter键监听，用于关闭更新模态框
        const enterKeyHandler = (e) => {
            if (e.key === 'Enter' && this.showUpdateModal && 
                (this.updateDataStatus === 'completed' || this.updateDataStatus === 'failed')) {
                this.closeUpdateModal();
            }
        };
        document.addEventListener('keydown', enterKeyHandler);
        this._enterKeyHandler = enterKeyHandler;
        
        try {
            await this.initializeUser();
            this.loadUserSettings();
            // 再次确保设置弹窗关闭
            this.showSettings = false;
            this.activeSubTab = 'records';
            // 根据当前激活的标签页加载数据
            await this.loadOrdersFromAPI();
            // 设置批量操作区域的 sticky top 值（在搜索区域下方）
            this.setupStickyPositions();
        } catch (error) {
            console.error('初始化失败:', error);
            alert(error.message || '初始化失敗，請重新登入');
            sessionStorage.removeItem('authInfo');
            window.location.href = 'login.html';
        }
    },
    methods: {
        async initializeUser() {
            const authInfo = getAuthInfo();
            if (!authInfo.token) {
                throw new Error('請先登入');
            }
            const profile = await apiFetch('/api/auth/me');
            const user = profile.user;
            this.userInfo = {
                username: user.username,
                name: user.name,
                role: user.role,
                jobNos: user.job_nos || []
            };
            // 所有用户统一显示100条
            this.defaultPageSize = 100;
            this.pageSize = this.defaultPageSize;
            sessionStorage.setItem('authInfo', JSON.stringify({
                token: authInfo.token,
                expires_at: authInfo.expires_at,
                user,
                login_time: authInfo.login_time
            }));
        },

        applyRoleFilter(records) {
            // admin和manager可以看到所有记录
            if (this.userInfo.role === 'admin' || this.userInfo.role === 'manager') {
                return records;
            }
            // user只能看到分配的Job No
            if (!Array.isArray(this.userInfo.jobNos) || this.userInfo.jobNos.length === 0) {
                return [];
            }
            const jobSet = new Set(this.userInfo.jobNos.map(job => String(job || '').trim().toUpperCase()));
            return records.filter(record => {
                const jobNo = String(record.jobNo || '').trim().toUpperCase();
                return jobSet.has(jobNo);
            });
        },

        async performSearch() {
            // 直接执行搜索，不再使用 debounce
            await this.executeSearch();
        },

        async executeSearch() {
            this.loading = true;
            try {
                const orderNoTrim = (this.searchQuery.orderNo || '').trim();
                const jobNoTrim = (this.searchQuery.jobNo || '').trim();
                const dnNoTrim = (this.searchQuery.dnNo || '').trim();
                const hasDate = !!(this.searchQuery.startDate || this.searchQuery.endDate);
                // Stocklist&Test Report 标签页支持 Order No、Job No、DD_No 和日期搜索
                // TR记录管理标签页支持 Order No、Job No 和日期搜索
                const hasCondition = orderNoTrim || jobNoTrim || dnNoTrim || hasDate;

                this.isSearching = hasCondition;

                // 日期搜索或Job No搜索时，每页记录上限设置为200；其他情况为100
                const perPageParam = (hasDate || jobNoTrim) ? 200 : 100;

                const params = new URLSearchParams({
                    page: '1',
                    per_page: String(perPageParam)
                });
                // 根据当前Tab决定使用哪个数据源
                if (this.activeSubTab === 'stocklist-test') {
                    params.set('tab', 'stocklist-test');
                } else {
                    params.set('tab', 'records');
                }
                if (orderNoTrim) params.set('order_no', orderNoTrim);
                if (jobNoTrim) params.set('job_no', jobNoTrim);
                if (dnNoTrim) params.set('dn_no', dnNoTrim);
                if (this.searchQuery.startDate) params.set('start_date', this.searchQuery.startDate);
                if (this.searchQuery.endDate) params.set('end_date', this.searchQuery.endDate);

                const result = await apiFetch(`/api/orders/list?${params.toString()}`);
                
                // 根据当前Tab使用不同的字段映射
                if (this.activeSubTab === 'stocklist-test') {
                    // Stocklist&Test Report 标签页：从 bbs_dd 表获取数据
                    this.records = result.data.map(order => ({
                        id: order.Order_No,
                        orderNo: order.Order_No ? order.Order_No.toString() : '',
                        orderDescription: order.Order_Description || '',
                        jobNo: order.Job_No ? order.Job_No.toString() : '',
                        jobsiteType: order.Jobsite_Type || '',
                        rmDnNo: order.rm_dn_no || '',
                        delDate: order.Del_Date || '',
                        status: (order.pdf_status || '').toLowerCase() || 'pending',
                        pdfPath: order.pdf_path || null,
                        generatedAt: order.generated_at || null
                    }));
                } else {
                    // TR记录管理标签页：从 TR_Report_Deduplication 表获取数据
                    this.records = result.data.map(order => ({
                        id: order.Order_No,
                        orderNo: order.Order_No ? order.Order_No.toString() : '',
                        orderDescription: order.Order_Description || '',
                        jobNo: order.Job_No ? order.Job_No.toString() : '',
                        client: order.Client || '',
                        jobsite: order.Jobsite || '',
                        jobsiteType: order.Jobsite_Type || '',
                        delDate: order.Del_Date || '',
                        wt: order.Wt || 0,
                        rmDnNo: order.rm_dn_no || '',
                        status: (order.pdf_status || '').toLowerCase() || 'pending',
                        pdfPath: order.pdf_path || null,
                        generatedAt: order.generated_at || null
                    }));
                }

                const filtered = this.applyRoleFilter(this.records);
                this.filteredRecords = filtered;
                // 日期搜索或Job No搜索时，每页记录上限设置为200；其他情况为100
                this.pageSize = perPageParam;
                // 使用API返回的总页数
                this.totalPagesComputed = result.pagination.total_pages || Math.max(Math.ceil(filtered.length / this.pageSize), 1);
                console.log('Search - API返回的分页信息:', {
                    hasCondition,
                    perPageParam,
                    total_pages: result.pagination.total_pages,
                    total_records: result.pagination.total_records,
                    received_records: result.data.length,
                    filtered_records: filtered.length,
                    computed_total_pages: this.totalPagesComputed
                });
                this.currentPage = 1;
            } catch (error) {
                console.error('搜索失败:', error);
                alert(error.message || '搜索失败，请稍后重试');
            } finally {
                this.loading = false;
            }
        },

        async loadSearchPage(page = 1) {
            /** 加载搜索结果的指定页 */
            this.loading = true;
            try {
                const orderNoTrim = (this.searchQuery.orderNo || '').trim();
                const jobNoTrim = (this.searchQuery.jobNo || '').trim();
                const dnNoTrim = (this.searchQuery.dnNo || '').trim();
                const hasDate = !!(this.searchQuery.startDate || this.searchQuery.endDate);

                // 日期搜索或Job No搜索时，每页记录上限设置为200；其他情况为100
                const perPageParam = (hasDate || jobNoTrim) ? 200 : 100;

                const params = new URLSearchParams({
                    page: String(page),
                    per_page: String(perPageParam)
                });
                // 根据当前Tab决定使用哪个数据源
                if (this.activeSubTab === 'stocklist-test') {
                    params.set('tab', 'stocklist-test');
                } else {
                    params.set('tab', 'records');
                }
                if (orderNoTrim) params.set('order_no', orderNoTrim);
                if (jobNoTrim) params.set('job_no', jobNoTrim);
                if (dnNoTrim) params.set('dn_no', dnNoTrim);
                if (this.searchQuery.startDate) params.set('start_date', this.searchQuery.startDate);
                if (this.searchQuery.endDate) params.set('end_date', this.searchQuery.endDate);

                const result = await apiFetch(`/api/orders/list?${params.toString()}`);
                
                // 根据当前Tab使用不同的字段映射
                if (this.activeSubTab === 'stocklist-test') {
                    // Stocklist&Test Report 标签页：从 bbs_dd 表获取数据
                    this.records = result.data.map(order => ({
                        id: order.Order_No,
                        orderNo: order.Order_No ? order.Order_No.toString() : '',
                        orderDescription: order.Order_Description || '',
                        jobNo: order.Job_No ? order.Job_No.toString() : '',
                        jobsiteType: order.Jobsite_Type || '',
                        rmDnNo: order.rm_dn_no || '',
                        delDate: order.Del_Date || '',
                        status: (order.pdf_status || '').toLowerCase() || 'pending',
                        pdfPath: order.pdf_path || null,
                        generatedAt: order.generated_at || null
                    }));
                } else {
                    // TR记录管理标签页：从 TR_Report_Deduplication 表获取数据
                    this.records = result.data.map(order => ({
                        id: order.Order_No,
                        orderNo: order.Order_No ? order.Order_No.toString() : '',
                        orderDescription: order.Order_Description || '',
                        jobNo: order.Job_No ? order.Job_No.toString() : '',
                        client: order.Client || '',
                        jobsite: order.Jobsite || '',
                        jobsiteType: order.Jobsite_Type || '',
                        delDate: order.Del_Date || '',
                        wt: order.Wt || 0,
                        rmDnNo: order.rm_dn_no || '',
                        status: (order.pdf_status || '').toLowerCase() || 'pending',
                        pdfPath: order.pdf_path || null,
                        generatedAt: order.generated_at || null
                    }));
                }

                const filtered = this.applyRoleFilter(this.records);
                this.filteredRecords = filtered;
                // 日期搜索或Job No搜索时，每页记录上限设置为200；其他情况为100
                this.pageSize = perPageParam;
                this.totalPagesComputed = result.pagination.total_pages || Math.max(Math.ceil(filtered.length / this.pageSize), 1);
                this.currentPage = page;
            } catch (error) {
                console.error('加载搜索页失败:', error);
                alert(error.message || '加载失败，请稍后重试');
            } finally {
                this.loading = false;
            }
        },

        async resetSearch() {
            this.searchQuery = { orderNo: '', jobNo: '', dnNo: '', startDate: '', endDate: '' };
            this.isSearching = false;
            this.pageSize = this.defaultPageSize;
            await this.loadOrdersFromAPI();
        },

        editRecord(record) {
            this.openEditModal(record.orderNo);
        },

        async openEditModal(orderNo) {
            if (this.userInfo.role !== 'admin') {
                alert('只有管理员可以编辑记录');
                return;
            }
            try {
                const result = await apiFetch(`/api/orders-gen-pdf/${orderNo}`);
                this.editData = JSON.parse(JSON.stringify(result.data));
                this._editOriginal = JSON.parse(JSON.stringify(result.data));
                this.editModalVisible = true;
            } catch (error) {
                console.error('加载编辑数据失败', error);
                alert(error.message || '加载编辑数据失败');
            }
        },

        closeEditModal() {
            this.editModalVisible = false;
            this.editData = { header: {}, lines: [] };
            this._editOriginal = null;
        },

        async saveEdits() {
            try {
                const orderNo = this.editData.header.Order_No;
                const header_updates = {};
                const headerKeys = ['Client','Jobsite','Job_No','PO_No_2','Del_Date','Ref_No','Order_Description','Supplier','Order_No'];
                headerKeys.forEach(k => {
                    const cur = this.editData.header[k];
                    const prev = this._editOriginal.header[k];
                    if (cur !== prev && cur !== undefined) header_updates[k] = cur;
                });
                const line_updates = [];
                for (let i = 0; i < this.editData.lines.length; i++) {
                    const cur = this.editData.lines[i];
                    const prev = (this._editOriginal.lines.find(l => l.id === cur.id)) || {};
                    const fields = ['Dia','Wt','Product','Grade','Pattern','Mill_Cert','Test_Cert2','Test_Cert1','Supplier','Stockist_Cert','PO_No_1','Tag_No','DN_No'];
                    const diff = { id: cur.id };
                    let changed = false;
                    fields.forEach(f => {
                        if (cur[f] !== prev[f]) { diff[f] = cur[f]; changed = true; }
                    });
                    if (changed) line_updates.push(diff);
                }
                if (Object.keys(header_updates).length === 0 && line_updates.length === 0) {
                    alert('未检测到变更');
                    return;
                }
                await apiFetch(`/api/orders-gen-pdf/${orderNo}/edit`, {
                    method: 'POST',
                    body: JSON.stringify({ header_updates, line_updates })
                });
                this.closeEditModal();
                if (this.isSearching) {
                    await this.executeSearch();
            } else {
                    await this.loadOrdersFromAPI(this.currentPage);
                }
                alert('已保存修改，状态已置为未生成');
            } catch (error) {
                console.error('保存失败', error);
                alert(error.message || '保存失败，请重试');
            }
        },

        async regeneratePDF(record) {
            console.log('[再次生成] 方法被调用');
            console.log('[再次生成] 记录信息:', record);
            console.log('[再次生成] 用户角色:', this.userInfo.role);
            console.log('[再次生成] 记录状态:', record.status);
            
            // admin和manager可以重新生成PDF
            if (this.userInfo.role !== 'admin' && this.userInfo.role !== 'manager') {
                alert('只有管理員和管理帳號可以重新生成 PDF');
                return;
            }
            
            console.log('[再次生成] 权限检查通过');
            
            if (!confirm(`确定要重新生成 Order ${record.orderNo} 的PDF吗？\n\n注意：这将覆盖现有的PDF文件。`)) {
                console.log('[再次生成] 用户取消了操作');
                return;
            }
            
            console.log('[再次生成] 用户确认，开始生成...');
            try {
                // 显示生成中状态
                record.status = 'generating';
                console.log('[再次生成] 发送请求到API...');
                
                const result = await apiFetch('/api/pdf/generate', {
                    method: 'POST',
                    body: JSON.stringify({ order_no: record.orderNo })
                });
                
                console.log('[再次生成] API响应:', result);
                
                if (result.success) {
                    alert(`PDF重新生成成功！`);
                    // 刷新数据以更新状态
                    if (this.isSearching) {
                        await this.executeSearch();
                    } else {
                        await this.loadOrdersFromAPI(this.currentPage);
                    }
                } else {
                    record.status = 'generated'; // 恢复状态
                    alert(result.error || 'PDF重新生成失败');
                }
            } catch (error) {
                record.status = 'generated'; // 恢复状态
                console.error('[再次生成] 错误详情:', error);
                console.error('[再次生成] 错误堆栈:', error.stack);
                alert(error.message || '重新生成PDF失败，请重试！');
            }
        },

        async generatePDF(record) {
            // admin和manager可以生成PDF
            if (this.userInfo.role !== 'admin' && this.userInfo.role !== 'manager') {
                alert('只有管理員和管理帳號可以生成 PDF');
                return;
            }
            if (!confirm(`确定要生成 Order ${record.orderNo} 的PDF吗？`)) {
                return;
            }
            try {
                // 显示生成中状态
                record.status = 'generating';
                
                // 显示进度提示
                const progressMsg = document.createElement('div');
                progressMsg.id = 'single-pdf-progress';
                progressMsg.style.cssText = 'position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); background: white; padding: 20px; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); z-index: 10000; min-width: 300px; text-align: center;';
                progressMsg.innerHTML = `
                    <h4>正在生成PDF...</h4>
                    <p>Order: ${record.orderNo}</p>
                    <div style="margin: 10px 0;">
                        <div style="width: 100%; height: 20px; background: #f0f0f0; border-radius: 10px; overflow: hidden;">
                            <div id="single-progress-bar" style="width: 0%; height: 100%; background: #4CAF50; transition: width 0.3s;"></div>
                        </div>
                    </div>
                    <p id="single-progress-text" style="margin: 10px 0; color: #666;">提交任务中...</p>
                `;
                document.body.appendChild(progressMsg);
                
                const updateProgress = (progress, text) => {
                    const bar = document.getElementById('single-progress-bar');
                    const textEl = document.getElementById('single-progress-text');
                    if (bar) bar.style.width = progress + '%';
                    if (textEl) textEl.textContent = text;
                };
                
                const result = await apiFetch('/api/pdf/generate', {
                    method: 'POST',
                    body: JSON.stringify({ order_no: record.orderNo })
                });
                
                if (!result.success || !result.task_id) {
                    document.body.removeChild(progressMsg);
                    throw new Error(result.error || '创建PDF生成任务失败');
                }
                
                const taskId = result.task_id;
                updateProgress(10, '任务已提交，等待处理...');
                
                // 轮询任务状态，直到完成或失败
                const maxAttempts = 120; // 最多轮询120次（4分钟）
                const pollInterval = 2000; // 每2秒轮询一次
                let attempts = 0;
                let taskCompleted = false;
                
                while (attempts < maxAttempts && !taskCompleted) {
                    await new Promise(resolve => setTimeout(resolve, pollInterval));
                    attempts++;
                    
                    try {
                        const statusResult = await apiFetch(`/api/pdf/task-status/${taskId}`);
                        
                        if (statusResult.success) {
                            const taskStatus = statusResult.status;
                            const progress = statusResult.progress || 0;
                            
                            if (taskStatus === 'completed') {
                                // 任务完成，更新状态
                                updateProgress(100, 'PDF生成完成！');
                                await new Promise(resolve => setTimeout(resolve, 500));
                                
                                document.body.removeChild(progressMsg);
                                record.status = 'generated';
                                record.pdfPath = statusResult.pdf_path || null;
                                taskCompleted = true;
                                
                                // 刷新数据以获取最新状态（从数据库读取）
                                if (this.isSearching) {
                                    await this.executeSearch();
                                } else {
                                    await this.loadOrdersFromAPI(this.currentPage);
                                }
                                
                                let successAlert = `PDF生成成功！\nOrder: ${record.orderNo}`;
                                if (statusResult.has_warning && statusResult.warning_message) {
                                    successAlert += `\n\n⚠️ ${statusResult.warning_message}`;
                                }
                                alert(successAlert);
                            } else if (taskStatus === 'failed') {
                                // 任务失败
                                document.body.removeChild(progressMsg);
                                record.status = 'pending';
                                taskCompleted = true;
                                throw new Error(statusResult.error_message || 'PDF生成失败');
                            } else if (taskStatus === 'processing') {
                                // 仍在处理中，更新进度提示
                                record.status = 'generating';
                                const progressText = statusResult.message || '正在生成PDF...';
                                updateProgress(Math.max(20, progress), progressText);
                            } else if (taskStatus === 'pending') {
                                updateProgress(15, '任务等待中...');
                            }
                        }
                    } catch (statusError) {
                        console.error('查询任务状态失败:', statusError);
                        // 继续轮询，不中断
                        if (attempts % 5 === 0) {
                            updateProgress(Math.min(90, 20 + attempts * 2), '正在查询任务状态...');
                        }
                    }
                }
                
                if (!taskCompleted) {
                    // 超时，但可能已经生成，刷新数据检查
                    document.body.removeChild(progressMsg);
                    record.status = 'pending';
                    if (this.isSearching) {
                        await this.executeSearch();
                    } else {
                        await this.loadOrdersFromAPI(this.currentPage);
                    }
                    alert('PDF生成超时，请稍后刷新页面查看状态');
                }
            } catch (error) {
                // 生成失败时恢复状态
                const progressMsg = document.getElementById('single-pdf-progress');
                if (progressMsg) document.body.removeChild(progressMsg);
                record.status = 'pending';
                console.error('生成PDF失败:', error);
                alert(error.message || '生成PDF時發生錯誤，請重試！');
            }
        },

        handleRowClick(record, event) {
            // 如果点击的是按钮、复选框或其他交互元素，不处理
            if (event.target.tagName === 'BUTTON' || 
                event.target.tagName === 'INPUT' || 
                event.target.closest('button') || 
                event.target.closest('input')) {
                return;
            }
            
            // 如果 PDF 已生成，点击行就下载
            if (record.status === 'generated') {
                this.downloadRecord(record);
            } else {
                // 如果 PDF 未生成，提示用户
                alert(`Order ${record.orderNo} 的PDF尚未生成，请先点击"📄 生成"按钮生成PDF。`);
            }
        },

        async downloadRecord(record) {
            if (record.status !== 'generated') {
                alert('该订单的PDF尚未生成，请先生成PDF！');
                return;
            }
            try {
                const authInfo = getAuthInfo();
                const headers = {};
                if (authInfo.token) headers['Authorization'] = `Bearer ${authInfo.token}`;
                const response = await fetch(buildApiUrl(`/api/pdf/download/${record.orderNo}`), { headers });
                if (!response.ok) {
                    let errorMsg = `下载失败：HTTP ${response.status}`;
                    try {
                        const data = await response.json();
                        if (data && data.error) errorMsg = `下载失败：${data.error}`;
                    } catch (_) {}
                    alert(errorMsg);
                    return;
                }
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `TR_${record.orderNo}.pdf`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
            } catch (error) {
                console.error('下载失败:', error);
                alert(error.message || '下載時發生錯誤，請重試！');
            }
        },

        async loadOrdersFromAPI(page = 1) {
            // 立即显示加载状态，提升用户体验
            this.loading = true;
            // 清空当前数据，避免显示旧数据
            this.filteredRecords = [];
            
            try {
                const startTime = performance.now();
                
                // 如果在搜索状态下，检查是否有日期搜索或Job No搜索
                let perPageValue = this.pageSize;
                if (this.isSearching) {
                    const hasDate = !!(this.searchQuery.startDate || this.searchQuery.endDate);
                    const jobNoTrim = (this.searchQuery.jobNo || '').trim();
                    // 日期搜索或Job No搜索时，每页记录上限设置为200；其他情况为100
                    if (hasDate || jobNoTrim) {
                        perPageValue = 200;
                    } else {
                        perPageValue = 100;
                    }
                }
                
                const params = new URLSearchParams({
                    page: String(page),
                    per_page: String(perPageValue)
                });
                // 根据当前Tab决定使用哪个数据源
                if (this.activeSubTab === 'stocklist-test') {
                    params.set('tab', 'stocklist-test');
                } else {
                    params.set('tab', 'records');
                }
                // 只有在搜索状态下才添加搜索参数
                if (this.isSearching) {
                    if (this.searchQuery.startDate) {
                        params.append('start_date', this.searchQuery.startDate);
                    }
                    if (this.searchQuery.endDate) {
                        params.append('end_date', this.searchQuery.endDate);
                    }
                    if (this.searchQuery.orderNo) {
                        params.append('order_no', this.searchQuery.orderNo);
                    }
                    if (this.searchQuery.jobNo) {
                        params.append('job_no', this.searchQuery.jobNo);
                    }
                    if (this.searchQuery.dnNo) {
                        params.append('dn_no', this.searchQuery.dnNo);
                    }
                }
                
                const result = await apiFetch(`/api/orders/list?${params.toString()}`);
                
                // 检查返回结果
                if (!result || !result.pagination) {
                    console.error('[分页] API 返回结果缺少分页信息:', result);
                    throw new Error('API 返回结果格式错误：缺少分页信息');
                }
                
                // 优化数据处理：使用更高效的方式
                const dataMapping = this.activeSubTab === 'stocklist-test' 
                    ? (order) => ({
                        id: order.Order_No,
                        orderNo: String(order.Order_No || ''),
                        orderDescription: order.Order_Description || '',
                        jobNo: String(order.Job_No || ''),
                        jobsiteType: order.Jobsite_Type || '',
                        rmDnNo: order.rm_dn_no || '',
                        delDate: order.Del_Date || '',
                        status: (order.pdf_status || 'pending').toLowerCase(),
                        pdfPath: order.pdf_path || null,
                        generatedAt: order.generated_at || null
                    })
                    : (order) => ({
                        id: order.Order_No,
                        orderNo: String(order.Order_No || ''),
                        orderDescription: order.Order_Description || '',
                        jobNo: String(order.Job_No || ''),
                        client: order.Client || '',
                        jobsite: order.Jobsite || '',
                        jobsiteType: order.Jobsite_Type || '',
                        delDate: order.Del_Date || '',
                        wt: order.Wt || 0,
                        rmDnNo: order.rm_dn_no || '',
                        status: (order.pdf_status || 'pending').toLowerCase(),
                        pdfPath: order.pdf_path || null,
                        generatedAt: order.generated_at || null
                    });
                
                // 批量处理数据，提升性能
                this.records = result.data.map(dataMapping);
                const filtered = this.applyRoleFilter(this.records);
                
                // 使用 Vue.nextTick 优化渲染性能
                await this.$nextTick();
                this.filteredRecords = filtered;
                
                // 如果在搜索状态下，更新 pageSize
                if (this.isSearching) {
                    this.pageSize = perPageValue;
                }
                
                const loadTime = performance.now() - startTime;
                console.log(`[性能] 数据加载耗时: ${loadTime.toFixed(2)}ms`);
                
                // 使用API返回的分页信息
                const apiCurrentPage = result.pagination.current_page || page;
                const apiTotalPages = result.pagination.total_pages || 1;
                const apiTotalRecords = result.pagination.total_records || 0;
                
                // 更新分页状态
                this.currentPage = apiCurrentPage;
                this.totalPagesComputed = apiTotalPages;
                
                // 确保当前页不超过总页数
                if (this.currentPage > this.totalPagesComputed) {
                    console.warn('[分页] 当前页超过总页数，调整到最后一页');
                    this.currentPage = Math.max(1, this.totalPagesComputed);
                }
                
                // 强制触发 Vue 响应式更新
                this.$nextTick(() => {
                    console.log('[分页] Vue 更新后的状态:', {
                        currentPage: this.currentPage,
                        totalPages: this.totalPages,
                        totalPagesComputed: this.totalPagesComputed
                    });
                });
            } catch (error) {
                console.error('[分页] 加载订单失败:', error);
                this.filteredRecords = [];
                alert(error.message || '加载订单失败，请稍后重试');
            } finally {
                // 确保加载状态被清除
                this.loading = false;
                // 恢复分页按钮状态
                this.$nextTick(() => {
                    const nextBtn = document.querySelector('.pagination button:last-child');
                    const prevBtn = document.querySelector('.pagination button:first-child');
                    if (nextBtn) nextBtn.disabled = this.currentPage >= this.totalPages;
                    if (prevBtn) prevBtn.disabled = this.currentPage <= 1;
                });
            }
        },

        async nextPage() {
            const current = this.currentPage;
            const computed = this.totalPagesComputed;
            
            // 直接使用 totalPagesComputed 作为判断
            if (current < computed) {
                const targetPage = current + 1;
                // 如果是搜索状态且有日期或Job No搜索，使用200；否则保持当前pageSize
                if (this.isSearching) {
                    const hasDate = !!(this.searchQuery.startDate || this.searchQuery.endDate);
                    const jobNoTrim = (this.searchQuery.jobNo || '').trim();
                    this.pageSize = (hasDate || jobNoTrim) ? 200 : 100;
                }
                // 禁用分页按钮，防止重复点击
                const nextBtn = document.querySelector('.pagination button:last-child');
                const prevBtn = document.querySelector('.pagination button:first-child');
                if (nextBtn) nextBtn.disabled = true;
                if (prevBtn) prevBtn.disabled = true;
                
                // 如果是搜索状态，使用搜索分页；否则使用普通分页
                if (this.isSearching) {
                    await this.loadSearchPage(targetPage);
                } else {
                    await this.loadOrdersFromAPI(targetPage);
                }
            }
        },

        async prevPage() {
            const current = this.currentPage;
            
            if (current > 1) {
                const targetPage = current - 1;
                // 如果是搜索状态且有日期或Job No搜索，使用200；否则保持当前pageSize
                if (this.isSearching) {
                    const hasDate = !!(this.searchQuery.startDate || this.searchQuery.endDate);
                    const jobNoTrim = (this.searchQuery.jobNo || '').trim();
                    this.pageSize = (hasDate || jobNoTrim) ? 200 : 100;
                }
                // 禁用分页按钮，防止重复点击
                const nextBtn = document.querySelector('.pagination button:last-child');
                const prevBtn = document.querySelector('.pagination button:first-child');
                if (nextBtn) nextBtn.disabled = true;
                if (prevBtn) prevBtn.disabled = true;
                
                // 如果是搜索状态，使用搜索分页；否则使用普通分页
                if (this.isSearching) {
                    await this.loadSearchPage(targetPage);
                } else {
                    await this.loadOrdersFromAPI(targetPage);
                }
            }
        },

        goToPageNum(page) {
            if (page >= 1 && page <= this.totalPages) {
                this.loadOrdersFromAPI(page);
            }
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

        async startUpdateAllTables(event) {
            // 仅允许真实用户点击触发，避免程序触发或异常回放导致重复启动
            if (event && event.isTrusted === false) {
                return;
            }
            if (this.updateDataLoading) {
                return;
            }

            // 确认操作
            if (!confirm('確定要更新所有數據嗎？此過程可能需要幾分鐘時間。')) {
                return;
            }

            this.updateDataLoading = true;
            this.showUpdateModal = true;
            this.updateDataStatus = 'running';
            this.updateDataMessage = '正在啟動更新流程...';

            try {
                // 启动更新
                const response = await apiFetch('/api/system/update-all-tables', {
                    method: 'POST'
                });

                if (response.success) {
                    this.updateDataMessage = '更新已啟動，正在後台執行...';
                    // 开始轮询检查状态
                    this.startCheckingUpdateStatus();
                } else {
                    throw new Error(response.error || '啟動更新失敗');
                }
            } catch (error) {
                console.error('啟動更新失敗:', error);
                this.updateDataStatus = 'failed';
                this.updateDataMessage = error.message || '啟動更新失敗，請稍後再試';
                this.updateDataLoading = false;
            }
        },

        startCheckingUpdateStatus() {
            // 清除之前的定时器
            if (this.updateCheckInterval) {
                clearInterval(this.updateCheckInterval);
            }

            let checkCount = 0;
            const maxChecks = 120; // 最多检查120次（10分钟，每5秒一次）

            this.updateCheckInterval = setInterval(async () => {
                checkCount++;
                
                try {
                    const response = await apiFetch('/api/system/check-update-status', {
                        method: 'GET'
                    });

                    if (response.success) {
                        const status = response.status;
                        const message = response.message || '';

                        if (status === 'completed') {
                            // 更新完成
                            clearInterval(this.updateCheckInterval);
                            this.updateCheckInterval = null;
                            this.updateDataStatus = 'completed';
                            this.updateDataMessage = message || '數據更新已完成！';
                            this.updateDataLoading = false;
                        } else if (status === 'failed') {
                            // 更新失败
                            clearInterval(this.updateCheckInterval);
                            this.updateCheckInterval = null;
                            this.updateDataStatus = 'failed';
                            this.updateDataMessage = message || '數據更新失敗，請查看日誌';
                            this.updateDataLoading = false;
                        } else if (status === 'running') {
                            // 仍在运行
                            this.updateDataMessage = message || '正在更新數據，請稍候...';
                        } else {
                            // 未知状态
                            if (checkCount >= maxChecks) {
                                clearInterval(this.updateCheckInterval);
                                this.updateCheckInterval = null;
                                this.updateDataStatus = 'failed';
                                this.updateDataMessage = '更新狀態檢查超時，請查看日誌確認狀態';
                                this.updateDataLoading = false;
                            }
                        }
                    }
                } catch (error) {
                    console.error('檢查更新狀態失敗:', error);
                    // 继续检查，不要因为一次检查失败就停止
                    if (checkCount >= maxChecks) {
                        clearInterval(this.updateCheckInterval);
                        this.updateCheckInterval = null;
                        this.updateDataStatus = 'failed';
                        this.updateDataMessage = '無法檢查更新狀態，請手動查看日誌';
                        this.updateDataLoading = false;
                    }
                }
            }, 5000); // 每5秒检查一次
        },

        closeUpdateModal() {
            // 清除定时器
            if (this.updateCheckInterval) {
                clearInterval(this.updateCheckInterval);
                this.updateCheckInterval = null;
            }
            this.showUpdateModal = false;
            this.updateDataLoading = false;
            this.updateDataStatus = 'running';
            this.updateDataMessage = '';
        },

        

        loadUserSettings() {
            const savedSettings = sessionStorage.getItem('userSettings');
            if (savedSettings) {
                this.userSettings = JSON.parse(savedSettings);
            } else {
                this.userSettings = {
                    avatar: this.userInfo.role === 'admin' ? 'admin' : 'default',
                    name: this.userInfo.name || '',
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
            this.userInfo.name = this.userSettings.name;
            sessionStorage.setItem('userSettings', JSON.stringify(this.userSettings));
            alert('设置已保存！');
            this.closeSettings();
        },

        getRoleDisplayName(role) {
            const roleMap = {
                'admin': '超级管理员',
                'manager': '管理帳號',
                'user': '普通用户'
            };
            return roleMap[role] || '用户';
        },

        getCurrentAvatar() {
            const selectedAvatar = this.avatarOptions.find(avatar => avatar.value === this.userSettings.avatar);
            return selectedAvatar ? selectedAvatar.icon : '👤';
        },

        toggleSelectAll() {
            const currentSelected = this.activeSubTab === 'records' 
                ? this.selectedRecords.records 
                : this.selectedRecords.stocklistTest;
            
            if (this.isAllSelected) {
                // 清空当前Tab的选择
                if (this.activeSubTab === 'records') {
                    this.selectedRecords.records = [];
                } else {
                    this.selectedRecords.stocklistTest = [];
                }
            } else {
                // 全选当前Tab的记录
                const allIds = this.filteredRecords.map(record => record.id);
                if (this.activeSubTab === 'records') {
                    this.selectedRecords.records = allIds;
                } else {
                    this.selectedRecords.stocklistTest = allIds;
                }
            }
        },

        clearSelection() {
            // 只清空当前Tab的选择
            if (this.activeSubTab === 'records') {
                this.selectedRecords.records = [];
            } else {
                this.selectedRecords.stocklistTest = [];
            }
        },

        async downloadByOrder() {
            const currentSelected = this.currentSelectedRecords;
            if (currentSelected.length === 0) {
                alert('请至少选择一个订单！');
                return;
            }

            // 直接使用 currentSelected 中的 id（它们就是 Order_No）
            // 因为 currentSelected 存储的是 record.id，而 record.id = order.Order_No
            // 这样即使搜索后 records 被更新，也能正确获取所有选中的订单号
            const orderNos = currentSelected
                .map(id => {
                    // id 就是 Order_No，但需要确保是数字或字符串格式
                    const orderNo = typeof id === 'number' ? id : parseInt(id);
                    return isNaN(orderNo) ? null : orderNo;
                })
                .filter(no => no != null && no > 0);

            if (orderNos.length === 0) {
                alert('选中的记录中没有有效的订单号！');
                return;
            }

            // 确认对话框
            const orderNosStr = orderNos.length <= 3 
                ? orderNos.join(', ') 
                : `${orderNos.slice(0, 3).join(', ')} 等 ${orderNos.length} 个`;
            
            if (!confirm(`确定要下载 ${orderNosStr} 的 Stockist&Test Report 文件吗？`)) {
                return;
            }

            // 显示进度条
            const total = orderNos.length;
            this.showDownloadProgress(total);
            this.updateDownloadProgress(0, total, '准备中......', '准备中', 'count');

            // 创建 AbortController 用于取消下载
            this.isCancelling = false;
            this.currentAbortController = new AbortController();

            try {
                const authInfo = getAuthInfo();
                const headers = {
                    'Content-Type': 'application/json'
                };
                if (authInfo.token) {
                    headers['Authorization'] = `Bearer ${authInfo.token}`;
                }

                let taskId;
                let zipFilename;

                if (orderNos.length === 1) {
                    // 单个订单：使用单个下载API（异步任务）
                    const orderNo = orderNos[0];
                    const response = await fetch(buildApiUrl(`/api/stockist-test/download-by-order/${orderNo}`), { 
                        method: 'GET',
                        headers,
                        signal: this.currentAbortController.signal
                    });
                    
                    if (!response.ok) {
                        throw await buildHttpError(response, '创建下载任务失败');
                    }
                    
                    const data = await response.json();
                    if (!data.success) {
                        throw new Error(data.error || '创建任务失败');
                    }
                    
                    taskId = data.task_id;
                    zipFilename = `Order_${orderNo}_Stockist_Test_${new Date().getTime()}.zip`;
                } else {
                    // 多个订单：使用批量下载API（异步任务）
                    const response = await fetch(buildApiUrl('/api/stockist-test/download-by-order-nos'), {
                        method: 'POST',
                        headers: headers,
                        body: JSON.stringify({ order_nos: orderNos }),
                        signal: this.currentAbortController.signal
                    });
                    
                    if (!response.ok) {
                        throw await buildHttpError(response, '创建批量下载任务失败');
                    }
                    
                    const data = await response.json();
                    if (!data.success) {
                        throw new Error(data.error || '创建任务失败');
                    }
                    
                    taskId = data.task_id;
                    const orderNosStr = orderNos.length <= 3 
                        ? orderNos.join('_') 
                        : `${orderNos.slice(0, 3).join('_')}_...`;
                    zipFilename = `${orderNosStr}_Stockist_Test_${new Date().getTime()}.zip`;
                }

                // 轮询任务状态
                await this.pollTaskStatus(taskId, zipFilename, total);

                const successMsg = orderNos.length === 1
                    ? `Order ${orderNos[0]} 的 Stockist&Test Report 文件下载完成！`
                    : `${orderNos.length} 个 Order 的 Stockist&Test Report 文件下载完成！`;
                alert(successMsg);
                this.clearSelection();

            } catch (error) {
                // 处理取消错误
                if (error.name === 'AbortError' || error.message === '下载已取消' || this.isCancelling) {
                    console.log('下载已取消');
                    this.updateDownloadProgress(0, total, '下载已取消', 'failed', 'count');
                    setTimeout(() => {
                        this.hideDownloadProgress();
                    }, 1000);
                    alert('下载已取消');
                } else {
                    this.hideDownloadProgress();
                    console.error('下载失败:', error);
                    alert(error.message || '下载时发生错误，请重试！');
                }
            } finally {
                this.isCancelling = false;
                this.currentAbortController = null;
            }
        },

        async downloadAllStockistNoFiles() {
            const currentSelected = this.currentSelectedRecords;
            if (currentSelected.length === 0) {
                alert('请至少选择一个订单！');
                return;
            }

            const orderNos = currentSelected
                .map(id => {
                    const orderNo = typeof id === 'number' ? id : parseInt(id);
                    return isNaN(orderNo) ? null : orderNo;
                })
                .filter(no => no != null && no > 0);

            if (orderNos.length === 0) {
                alert('选中的记录中没有有效的订单号！');
                return;
            }

            const orderNosStr = orderNos.length <= 3
                ? orderNos.join(', ')
                : `${orderNos.slice(0, 3).join(', ')} 等 ${orderNos.length} 个`;

            if (!confirm(`确定要下载 ${orderNosStr} 的全部 Stockist No 文件吗？\n（系统会自动去重，不按 Item 分类）`)) {
                return;
            }

            const total = orderNos.length;
            this.showDownloadProgress(total);
            this.updateDownloadProgress(0, total, '准备中......', '准备中', 'count');

            this.isCancelling = false;
            this.currentAbortController = new AbortController();

            try {
                const authInfo = getAuthInfo();
                const headers = {
                    'Content-Type': 'application/json'
                };
                if (authInfo.token) {
                    headers['Authorization'] = `Bearer ${authInfo.token}`;
                }

                const response = await fetch(buildApiUrl('/api/stockist-test/download-all-stockist-nos'), {
                    method: 'POST',
                    headers: headers,
                    body: JSON.stringify({ order_nos: orderNos }),
                    signal: this.currentAbortController.signal
                });

                if (!response.ok) {
                    throw await buildHttpError(response, '创建扁平Stockist下载任务失败');
                }

                const data = await response.json();
                if (!data.success) {
                    throw new Error(data.error || '创建任务失败');
                }

                const taskId = data.task_id;
                const orderNosFileTag = orderNos.length <= 3
                    ? orderNos.join('_')
                    : `${orderNos.slice(0, 3).join('_')}_...`;
                const zipFilename = `${orderNosFileTag}_All_Stockist_No_${new Date().getTime()}.zip`;

                await this.pollTaskStatus(taskId, zipFilename, total);

                const successMsg = orderNos.length === 1
                    ? `Order ${orderNos[0]} 的全部 Stockist No 文件下载完成！`
                    : `${orderNos.length} 个 Order 的全部 Stockist No 文件下载完成！`;
                alert(successMsg);
                this.clearSelection();

            } catch (error) {
                if (error.name === 'AbortError' || error.message === '下载已取消' || this.isCancelling) {
                    console.log('下载已取消');
                    this.updateDownloadProgress(0, total, '下载已取消', 'failed', 'count');
                    setTimeout(() => {
                        this.hideDownloadProgress();
                    }, 1000);
                    alert('下载已取消');
                } else {
                    this.hideDownloadProgress();
                    console.error('下载失败:', error);
                    alert(error.message || '下载时发生错误，请重试！');
                }
            } finally {
                this.isCancelling = false;
                this.currentAbortController = null;
            }
        },

        async downloadByDdNo() {
            const currentSelected = this.currentSelectedRecords;
            if (currentSelected.length === 0) {
                alert('请至少选择一个订单！');
                return;
            }

            // 直接使用 currentSelected 中的 id（它们就是 Order_No）
            const orderNos = currentSelected
                .map(id => {
                    const orderNo = typeof id === 'number' ? id : parseInt(id);
                    return isNaN(orderNo) ? null : orderNo;
                })
                .filter(no => no != null && no > 0);

            if (orderNos.length === 0) {
                alert('选中的记录中没有有效的订单号！');
                return;
            }

            // 确认对话框
            const orderNosStr = orderNos.length <= 3 
                ? orderNos.join(', ') 
                : `${orderNos.slice(0, 3).join(', ')} 等 ${orderNos.length} 个`;
            
            if (!confirm(`确定要下载 ${orderNosStr} 对应的所有 DD_No 的 Stockist&Test Report 文件吗？\n（系统会自动按 DD_No 分组并去重）`)) {
                return;
            }

            // 显示进度条
            const total = orderNos.length;
            this.showDownloadProgress(total);
            this.updateDownloadProgress(0, total, '准备中......', '准备中', 'count');

            // 创建 AbortController 用于取消下载
            this.isCancelling = false;
            this.currentAbortController = new AbortController();

            try {
                const authInfo = getAuthInfo();
                const headers = {
                    'Content-Type': 'application/json'
                };
                if (authInfo.token) {
                    headers['Authorization'] = `Bearer ${authInfo.token}`;
                }

                // 使用批量按 DD_No 下载API（异步任务）
                const response = await fetch(buildApiUrl('/api/stockist-test/download-by-order-nos-grouped-by-dd-no'), {
                    method: 'POST',
                    headers: headers,
                    body: JSON.stringify({ order_nos: orderNos }),
                    signal: this.currentAbortController.signal
                });

                if (!response.ok) {
                    throw await buildHttpError(response, '创建按DD_No分组下载任务失败');
                }

                const data = await response.json();
                if (!data.success) {
                    throw new Error(data.error || '创建任务失败');
                }

                const taskId = data.task_id;
                const orderNosStr = orderNos.length <= 3 
                    ? orderNos.join('_') 
                    : `${orderNos.slice(0, 3).join('_')}_...`;
                const zipFilename = `${orderNosStr}_DD_No_Stockist_Test_${new Date().getTime()}.zip`;

                // 轮询任务状态
                await this.pollTaskStatus(taskId, zipFilename, total);

                const successMsg = orderNos.length === 1
                    ? `Order ${orderNos[0]} 对应的 DD_No 的 Stockist&Test Report 文件下载完成！`
                    : `${orderNos.length} 个 Order 对应的所有 DD_No 的 Stockist&Test Report 文件下载完成！`;
                alert(successMsg);
                this.clearSelection();

            } catch (error) {
                // 处理取消错误
                if (error.name === 'AbortError' || error.message === '下载已取消' || this.isCancelling) {
                    console.log('下载已取消');
                    this.updateDownloadProgress(0, total, '下载已取消', 'failed', 'count');
                    setTimeout(() => {
                        this.hideDownloadProgress();
                    }, 1000);
                    alert('下载已取消');
                } else {
                    this.hideDownloadProgress();
                    console.error('下载失败:', error);
                    alert(error.message || '下载时发生错误，请重试！');
                }
            } finally {
                this.isCancelling = false;
                this.currentAbortController = null;
            }
        },

        async downloadByDate() {
            const currentSelected = this.currentSelectedRecords;
            if (currentSelected.length === 0) {
                alert('请至少选择一个订单！');
                return;
            }
            

            // 直接使用 currentSelected 中的 id（它们就是 Order_No）
            const orderNos = currentSelected
                .map(id => {
                    const orderNo = typeof id === 'number' ? id : parseInt(id);
                    return isNaN(orderNo) ? null : orderNo;
                })
                .filter(no => no != null && no > 0);

            if (orderNos.length === 0) {
                alert('选中的记录中没有有效的订单号！');
                return;
            }

            // 确认对话框
            const orderNosStr = orderNos.length <= 3 
                ? orderNos.join(', ') 
                : `${orderNos.slice(0, 3).join(', ')} 等 ${orderNos.length} 个`;
            
            if (!confirm(`确定要下载 ${orderNosStr} 对应的所有日期的 Stockist&Test Report 文件吗？\n（系统会自动按日期分组，同一天的所有stockist放到同一个文件夹并去重）`)) {
                return;
            }

            // 创建 AbortController 用于取消下载
            this.isCancelling = false;
            this.currentAbortController = new AbortController();

            // 声明 dates 变量，使其在整个函数作用域内可用
            let dates = [];
            let total = 1;

            try {
                const authInfo = getAuthInfo();
                if (!authInfo || !authInfo.token) {
                    alert('请先登录！');
                    return;
                }
                
                const headers = {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${authInfo.token}`
                };

                // 先获取日期数量（静默获取，不显示进度条，优化后的批量查询应该很快）
                const dateCountResponse = await fetch(buildApiUrl('/api/stockist-test/get-date-count'), {
                    method: 'POST',
                    headers: headers,
                    body: JSON.stringify({ order_nos: orderNos }),
                    signal: this.currentAbortController.signal
                });

                if (!dateCountResponse.ok) {
                    throw await buildHttpError(dateCountResponse, '获取日期数量失败');
                }

                const dateCountData = await dateCountResponse.json();
                total = dateCountData.date_count || 1;
                dates = dateCountData.dates || [];
                console.log('[下载] 日期数量:', total, '日期列表:', dates);
                
                // 现在显示进度条
                this.showDownloadProgress(total);
                this.updateDownloadProgress(0, total, '准备中......', '准备中', 'count');

                // 使用批量按日期下载API（异步任务）
                const response = await fetch(buildApiUrl('/api/stockist-test/download-by-order-nos-grouped-by-date'), {
                    method: 'POST',
                    headers: headers,
                    body: JSON.stringify({ order_nos: orderNos }),
                    signal: this.currentAbortController.signal
                });

                if (!response.ok) {
                    throw await buildHttpError(response, '创建按日期分组下载任务失败');
                }

                const data = await response.json();
                if (!data.success) {
                    throw new Error(data.error || '创建任务失败');
                }

                const taskId = data.task_id;
                const orderNosStr = orderNos.length <= 3 
                    ? orderNos.join('_') 
                    : `${orderNos.slice(0, 3).join('_')}_...`;
                const zipFilename = `${orderNosStr}_Date_Stockist_Test_${new Date().getTime()}.zip`;

                // 轮询任务状态
                await this.pollTaskStatus(taskId, zipFilename, total);

                const successMsg = orderNos.length === 1
                    ? `Order ${orderNos[0]} 对应的所有日期的 Stockist&Test Report 文件下载完成！`
                    : `${orderNos.length} 个 Order 对应的所有日期的 Stockist&Test Report 文件下载完成！`;
                alert(successMsg);
                this.clearSelection();

            } catch (error) {
                // 处理取消错误
                if (error.name === 'AbortError' || error.message === '下载已取消' || this.isCancelling) {
                    console.log('下载已取消');
                    this.updateDownloadProgress(0, total || 1, '下载已取消', 'failed', 'count');
                    setTimeout(() => {
                        this.hideDownloadProgress();
                    }, 1000);
                    alert('下载已取消');
                } else {
                    this.hideDownloadProgress();
                    console.error('下载失败:', error);
                    alert(error.message || '下载时发生错误，请重试！');
                }
            } finally {
                this.isCancelling = false;
                this.currentAbortController = null;
            }
        },

        async batchDownload() {
            if (!this.hasSelectedGeneratedRecords) {
                alert('请选择至少一条已生成的记录！');
                return;
            }

            const currentSelected = this.currentSelectedRecords;
            const selectedGeneratedRecords = currentSelected
                .map(id => this.records.find(r => r.id === id))
                .filter(record => record && record.status === 'generated');

            console.log('[批量下载] 总选择记录数:', currentSelected.length);
            console.log('[批量下载] 已生成记录数:', selectedGeneratedRecords.length);
            console.log('[批量下载] 已生成记录:', selectedGeneratedRecords.map(r => `${r.orderNo}(${r.status})`));

            if (selectedGeneratedRecords.length === 0) {
                alert('没有可下载的记录！请确保选择的记录状态为"已生成"。');
                return;
            }

            const confirmMessage = `确定要下载 ${selectedGeneratedRecords.length} 个PDF文件吗？\n\n选中的记录：\n${selectedGeneratedRecords.slice(0, 5).map(r => `- ${r.orderNo} (${r.orderDescription})`).join('\n')}${selectedGeneratedRecords.length > 5 ? `\n... 还有 ${selectedGeneratedRecords.length - 5} 个` : ''}`;
            if (!confirm(confirmMessage)) {
                return;
            }

            this.isCancelling = false;
            this.currentAbortController = new AbortController();

            try {
                // 统一使用打包下载（ZIP），即使只有1个文件
                this.showDownloadProgress(1);
                this.updateDownloadProgress(1, 1, '正在打包...');

                const orderNos = selectedGeneratedRecords.map(r => {
                    const orderNo = r.orderNo;
                    const num = parseInt(orderNo, 10);
                    return isNaN(num) ? orderNo : num;
                });
                
                const authInfo = getAuthInfo();
                const headers = { 'Content-Type': 'application/json' };
                if (authInfo.token) {
                    headers['Authorization'] = `Bearer ${authInfo.token}`;
                }
                
                const response = await fetch(buildApiUrl('/api/pdf/batch-download'), {
                    method: 'POST',
                    headers,
                    body: JSON.stringify({ order_nos: orderNos }),
                    signal: this.currentAbortController.signal
                });
                
                if (!response.ok) {
                    let errorMsg = `批量下载失败：HTTP ${response.status}`;
                    try {
                        const data = await response.json();
                        if (data && data.error) {
                            errorMsg = `批量下载失败：${data.error}`;
                            // 如果有详细信息，添加到错误消息中
                            if (data.not_generated && data.not_generated.length > 0) {
                                errorMsg += `\n未生成的订单：${data.not_generated.slice(0, 10).join(', ')}${data.not_generated.length > 10 ? '...' : ''}`;
                            }
                            if (data.missing && data.missing.length > 0) {
                                errorMsg += `\n缺失文件的订单：${data.missing.slice(0, 10).join(', ')}${data.missing.length > 10 ? '...' : ''}`;
                            }
                            if (data.unauthorized && data.unauthorized.length > 0) {
                                errorMsg += `\n无权限访问的订单：${data.unauthorized.slice(0, 10).join(', ')}${data.unauthorized.length > 10 ? '...' : ''}`;
                            }
                        }
                    } catch (_) {
                        try {
                            const text = await response.text();
                            if (text) errorMsg += `\n${text}`;
                        } catch (_) {}
                    }
                    this.hideDownloadProgress();
                    alert(errorMsg);
                    return;
                }

                const blob = await response.blob();
                if (blob.size === 0) {
                this.hideDownloadProgress();
                    alert('批量下载失败：服务器返回了空文件');
                    return;
                }

                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `Orders_${new Date().getTime()}.zip`;
                a.style.display = 'none';
                document.body.appendChild(a);
                a.click();
                await new Promise(resolve => setTimeout(resolve, 200));
                document.body.removeChild(a);
                setTimeout(() => {
                    window.URL.revokeObjectURL(url);
                }, 2000);

                this.hideDownloadProgress();
                alert(`批量下载完成！共下载 ${selectedGeneratedRecords.length} 个PDF文件（已打包为ZIP）。`);

                this.clearSelection();

            } catch (error) {
                if (error.name === 'AbortError' || this.isCancelling) {
                    console.log('下载被取消');
                    this.hideDownloadProgress();
                    return;
                }
                console.error('批量下载失败:', error);
                console.error('错误详情:', {
                    message: error.message,
                    stack: error.stack,
                    name: error.name
                });
                this.hideDownloadProgress();
                let errorMsg = '批量下载失败，请重试！';
                if (error.message) {
                    errorMsg += `\n错误信息：${error.message}`;
                }
                alert(errorMsg);
            } finally {
                this.isCancelling = false;
                this.currentAbortController = null;
            }
        },

        async downloadSingleRecord(record, signal = null) {
            console.log(`正在下载: ${record.orderNo} - ${record.orderDescription}`);
            try {
                const authInfo = getAuthInfo();
                const headers = {};
                if (authInfo.token) {
                    headers['Authorization'] = `Bearer ${authInfo.token}`;
                }
                const fetchOptions = { headers };
                if (signal) {
                    fetchOptions.signal = signal;
                }
                const response = await fetch(buildApiUrl(`/api/pdf/download/${record.orderNo}`), fetchOptions);
                if (!response.ok) {
                    let errorMsg = `下载失败：HTTP ${response.status}`;
                    try {
                        const data = await response.json();
                        if (data && data.error) errorMsg = `下载失败：${data.error}`;
                    } catch (_) {}
                    throw new Error(errorMsg);
                }
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `TR_${record.orderNo}.pdf`;
                a.style.display = 'none';
                document.body.appendChild(a);
                a.click();
                // 等待一小段时间确保下载开始
                await new Promise(resolve => setTimeout(resolve, 100));
                document.body.removeChild(a);
                // 延迟释放URL，确保下载完成
                setTimeout(() => {
                    window.URL.revokeObjectURL(url);
                }, 1000);
                console.log(`Downloaded PDF for Order ${record.orderNo}`);
                return true;
            } catch (error) {
                console.error('下载失败:', error);
                throw error;
            }
        },

        showDownloadProgress(total) {
            // 如果已经显示，不重复创建
            if (document.getElementById('download-progress')) {
                return;
            }

            const title = '批量下载中...';
            const subtitle = '';

            const progressHtml = `
                <div id="download-progress" class="download-progress-overlay">
                    <div class="download-progress-content">
                        <h3>${title}</h3>
                        ${subtitle}
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: 0%"></div>
                        </div>
                        <div class="progress-text">准备中......</div>
                        <div class="progress-details"></div>
                        <div class="progress-actions">
                            <button class="stop-btn" @click="stopDownload">停止下载</button>
                        </div>
                    </div>
                </div>
            `;
            document.body.insertAdjacentHTML('beforeend', progressHtml);
            const stopBtn = document.querySelector('#download-progress .stop-btn');
            if (stopBtn) {
                stopBtn.addEventListener('click', () => this.stopDownload());
            }
            this.downloadProgressVisible = true;
        },

        async pollTaskStatus(taskId, zipFilename, total) {
            const authInfo = getAuthInfo();
            const headers = {
                'Content-Type': 'application/json'
            };
            if (authInfo.token) {
                headers['Authorization'] = `Bearer ${authInfo.token}`;
            }

            const maxAttempts = 2400; // 最多轮询20分钟（每200毫秒一次，或更短）
            let attempts = 0;
            let pollInterval;
            let lastProgress = 0;
            let currentPollInterval = 200; // 初始轮询间隔：200ms（更快响应）

            return new Promise((resolve, reject) => {
                // 立即执行第一次查询，不等待
                const checkStatus = async () => {
                    attempts++;
                    
                    // 检查是否被取消
                    if (this.isCancelling) {
                        clearInterval(pollInterval);
                        reject(new Error('下载已取消'));
                        return;
                    }

                    try {
                        // 使用带超时和重试的 fetch
                        const response = await fetchWithRetry(
                            buildApiUrl(`/api/download/task-status/${taskId}`),
                            {
                                headers,
                                signal: this.currentAbortController.signal
                            },
                            30000, // 30秒超时（轮询请求应该快速响应）
                            2,     // 最多重试2次
                            2000   // 初始重试延迟2秒
                        );

                        if (!response.ok) {
                            throw await buildHttpError(response, '查询下载任务状态失败');
                        }

                        const data = await response.json();
                        if (!data.success) {
                            throw new Error(data.error || '查询任务状态失败');
                        }

                        const status = data.status;
                        const progress = data.progress || 0;
                        const processedFiles = data.processed_files || 0;
                        const totalFiles = data.total_files || total;

                        // 更新进度显示
                        if (status === 'processing') {
                            const progressText = totalFiles > 0 
                                ? `正在处理: ${processedFiles}/${totalFiles} 个文件`
                                : `正在处理...`;
                            this.updateDownloadProgress(
                                Math.max(processedFiles, Math.floor(progress * total / 100)), 
                                totalFiles || total, 
                                progressText, 
                                'downloading', 
                                'count'
                            );
                            
                            // 动态调整轮询间隔：进度越高，检查越频繁
                            let newInterval = 200; // 默认200ms
                            if (progress > 95) {
                                newInterval = 100; // 95%以上：100ms
                            } else if (progress > 80) {
                                newInterval = 150; // 80-95%：150ms
                            } else if (progress > 50) {
                                newInterval = 200; // 50-80%：200ms
                            } else {
                                newInterval = 300; // 0-50%：300ms（可以稍慢）
                            }
                            
                            // 如果间隔改变，重新设置定时器
                            if (newInterval !== currentPollInterval) {
                                clearInterval(pollInterval);
                                currentPollInterval = newInterval;
                                pollInterval = setInterval(checkStatus, currentPollInterval);
                            }
                            
                            lastProgress = progress;
                        } else if (status === 'completed') {
                            clearInterval(pollInterval);
                            const warningMessage = data.has_warning ? (data.warning_message || '') : '';
                            
                            // 立即开始下载，不等待任何UI更新
                            const downloadUrl = buildApiUrl(`/api/download/download/${taskId}`);
                            console.log('[下载] 任务完成，立即开始下载:', downloadUrl);
                            
                            // 使用带超时和重试的 fetch（大文件下载需要更长时间）
                            const downloadPromise = fetchWithRetry(
                                downloadUrl,
                                {
                                    headers,
                                    signal: this.currentAbortController.signal
                                },
                                1800000, // 30分钟超时（大文件下载）
                                3,       // 最多重试3次
                                5000     // 初始重试延迟5秒
                            ).then(async downloadResponse => {
                                // 在获取响应后立即更新UI
                                this.updateDownloadProgress(totalFiles || total, totalFiles || total, '正在下载...', 'downloading', 'count');
                                
                                if (!downloadResponse.ok) {
                                    throw await buildHttpError(downloadResponse, '下载文件失败');
                                }
                                
                                // 获取blob
                                return downloadResponse.blob();
                            }).then(blob => {
                                console.log('[下载] 文件大小:', blob.size, 'bytes');
                                
                                if (blob.size === 0) {
                                    throw new Error('下载的文件为空');
                                }

                                // 立即触发浏览器下载
                                const url = window.URL.createObjectURL(blob);
                                const a = document.createElement('a');
                                a.href = url;
                                a.download = zipFilename;
                                a.style.display = 'none';
                                document.body.appendChild(a);
                                a.click();
                                console.log('[下载] 触发下载:', zipFilename);
                                
                                // 立即清理DOM元素，异步清理URL
                                document.body.removeChild(a);
                                setTimeout(() => {
                                    window.URL.revokeObjectURL(url);
                                }, 100);

                                // 更新进度为完成
                                this.updateDownloadProgress(totalFiles || total, totalFiles || total, '下载完成', 'complete', 'count');

                                if (warningMessage) {
                                    alert(`下载完成，但检测到以下缺失：\n${warningMessage}`);
                                }

                                // 延迟隐藏进度条
                                setTimeout(() => {
                                    this.hideDownloadProgress();
                                }, 1000);

                                resolve();
                            }).catch(downloadError => {
                                console.error('[下载] 下载文件时出错:', downloadError);
                                this.updateDownloadProgress(0, total, `下载失败: ${downloadError.message}`, 'failed', 'count');
                                setTimeout(() => {
                                    this.hideDownloadProgress();
                                }, 2000);
                                reject(downloadError);
                            });
                            
                            // 在开始 fetch 的同时更新UI为"处理完成，准备下载"
                            this.updateDownloadProgress(totalFiles || total, totalFiles || total, '处理完成，准备下载...', 'complete', 'count');
                            
                            // 不等待 fetch 完成，直接返回（让 Promise 在 fetch 完成后 resolve）
                            return;
                        } else if (status === 'failed') {
                            clearInterval(pollInterval);
                            const errorMsg = data.error_message || '任务处理失败';
                            this.updateDownloadProgress(0, total, `失败: ${errorMsg}`, 'failed', 'count');
                            setTimeout(() => {
                                this.hideDownloadProgress();
                            }, 2000);
                            reject(new Error(errorMsg));
                        } else if (status === 'pending') {
                            // 任务还在等待处理
                            this.updateDownloadProgress(0, total, '等待处理...', 'pending', 'count');
                        }

                        // 检查是否超过最大尝试次数
                        if (attempts >= maxAttempts) {
                            clearInterval(pollInterval);
                            reject(new Error('任务处理超时，请稍后重试'));
                        }
                    } catch (error) {
                        // 处理取消错误
                        if (error.name === 'AbortError' || this.isCancelling) {
                            clearInterval(pollInterval);
                            reject(new Error('下载已取消'));
                            return;
                        }
                        
                        // 如果达到最大尝试次数，停止轮询
                        if (attempts >= maxAttempts) {
                            clearInterval(pollInterval);
                            let errorMsg = `查询任务状态超时：已尝试 ${attempts} 次`;
                            if (error.message) {
                                errorMsg += ` (${error.message})`;
                            }
                            reject(new Error(errorMsg));
                            return;
                        }
                        
                        // 网络错误：记录并继续轮询（可能是临时网络问题）
                        console.error(`[轮询错误] 第 ${attempts} 次查询失败:`, error);
                        
                        // 如果是网络超时或连接错误，等待更长时间后重试
                        if (error.message && (error.message.includes('超时') || error.message.includes('网络') || error.message.includes('连接'))) {
                            // 等待5秒后继续（不增加 attempts，因为这是网络问题）
                            await new Promise(resolve => setTimeout(resolve, 5000));
                        }
                    }
                };
                
                // 立即执行第一次查询
                checkStatus();
                
                // 然后每200毫秒轮询一次（更快响应）
                pollInterval = setInterval(checkStatus, currentPollInterval);
            });
        },

        updateDownloadProgress(current, total, currentRecord, status = 'downloading', progressType = 'count') {
            const progressFill = document.querySelector('.progress-fill');
            const progressText = document.querySelector('.progress-text');
            const progressDetails = document.querySelector('.progress-details');
            if (progressFill && progressText && progressDetails) {
                const safeCurrent = Math.max(0, Math.min(current, total));
                let percentage = 0;
                if (total > 0) {
                    percentage = (safeCurrent / total) * 100;
                    if (safeCurrent === total) percentage = 100;
                }
                
                // 处理准备中状态的动画
                if (status === '准备中') {
                    progressFill.classList.add('preparing');
                    progressFill.classList.remove('complete');
                } else {
                    progressFill.classList.remove('preparing');
                    progressFill.style.width = `${percentage}%`;
                    if (percentage === 100) progressFill.classList.add('complete');
                }
                
                // 根据进度类型显示不同的格式
                if (progressType === 'percentage') {
                    // 按时间下载：显示百分比
                    if (status === '准备中') {
                        // 准备中状态：只显示"准备中......"，不显示百分比
                        progressText.textContent = '准备中......';
                        progressDetails.textContent = '';  // 准备中时不显示详细信息
                    } else {
                        progressText.textContent = `${Math.round(percentage)}%`;
                        if (status === 'downloading') {
                            if (typeof currentRecord === 'string' && currentRecord.trim().length > 0) {
                                progressDetails.textContent = currentRecord;
                            } else {
                                progressDetails.textContent = '正在下载...';
                            }
                        } else if (status === 'complete') {
                            progressDetails.textContent = '下载完成';
                        } else {
                            progressDetails.textContent = currentRecord || '准备中......';
                        }
                    }
                } else {
                    // 按Order或按DD_No下载：显示 1/10 格式
                    if (status === '准备中') {
                        // 准备中状态：只显示"准备中......"，不显示进度数字
                        progressText.textContent = '准备中......';
                        progressDetails.textContent = '';  // 准备中时不显示详细信息
                    } else if (status === 'downloading') {
                        progressText.textContent = `${safeCurrent}/${total}`;
                        if (typeof currentRecord === 'string' && currentRecord.trim().length > 0) {
                            const trimmed = currentRecord.trim();
                            if (/正在/.test(trimmed)) {
                                progressDetails.textContent = trimmed;
                            } else {
                                progressDetails.textContent = trimmed;
                            }
                        } else {
                            progressDetails.textContent = `正在下载 ${safeCurrent}/${total}`;
                        }
                    } else if (status === 'complete') {
                        progressText.textContent = `${safeCurrent}/${total}`;
                        progressDetails.textContent = safeCurrent === total ? `全部完成` : `完成: ${currentRecord}`;
                    } else {
                        // 其他状态也显示进度数字
                        progressText.textContent = `${safeCurrent}/${total}`;
                        progressDetails.textContent = currentRecord || '准备中......';
                    }
                }
            }
        },


        hideDownloadProgress() {
            const progressOverlay = document.getElementById('download-progress');
            if (progressOverlay) {
                progressOverlay.remove();
            }
            this.downloadProgressVisible = false;
        },

        delay(ms) {
            return new Promise(resolve => setTimeout(resolve, ms));
        },
        
        // ============= API 方法 =============
        
        async batchGenerate() {
            if (!this.hasSelectedPendingRecords) {
                alert('请选择至少一条未生成的记录！');
                return;
            }

            const currentSelected = this.currentSelectedRecords;
            const selectedPendingRecords = currentSelected
                .map(id => this.records.find(r => r.id === id))
                .filter(record => record && record.status !== 'generated');

            if (selectedPendingRecords.length === 0) {
                alert('没有可生成的记录！');
                return;
            }

            const confirmMessage = `确定要批量生成 ${selectedPendingRecords.length} 个订单的PDF吗？\n\n选中的记录：\n${selectedPendingRecords.slice(0, 5).map(r => `- ${r.orderNo} (${r.orderDescription || ''})`).join('\n')}${selectedPendingRecords.length > 5 ? `\n... 还有 ${selectedPendingRecords.length - 5} 个` : ''}`;
            if (!confirm(confirmMessage)) return;

            this.isCancelling = false;
            this.currentAbortController = new AbortController();

            try {
                this.showGenerateProgress(selectedPendingRecords.length);

                let successCount = 0;
                let failCount = 0;
                const failedOrders = [];
                const warningOrders = new Set();

                for (let i = 0; i < selectedPendingRecords.length; i++) {
                    if (this.isCancelling) {
                        console.log('用户取消了批量生成');
                        this.hideGenerateProgress();
                        alert(`生成已取消。\n已生成: ${successCount} 个\n失败: ${failCount} 个`);
                        
                        if (this.isSearching) {
                            await this.executeSearch();
                        } else {
                            await this.loadOrdersFromAPI(this.currentPage);
                        }
                        return;
                    }

                    const record = selectedPendingRecords[i];
                    record.status = 'generating';
                    this.updateGenerateProgress(i, selectedPendingRecords.length, record.orderNo, 'processing');

                    try {
                        // 提交生成任务
                        const resp = await apiFetch('/api/pdf/generate', {
                            method: 'POST',
                            body: JSON.stringify({ order_no: record.orderNo }),
                            signal: this.currentAbortController.signal
                        });
                        
                        if (!resp.success || !resp.task_id) {
                            throw new Error(resp.error || '创建PDF生成任务失败');
                        }
                        
                        const taskId = resp.task_id;
                        this.updateGenerateProgress(i, selectedPendingRecords.length, record.orderNo, 'processing', `任务已提交，等待处理...`);
                        
                        // 轮询任务状态，直到完成或失败
                        const maxAttempts = 120; // 最多轮询120次（4分钟）
                        const pollInterval = 2000; // 每2秒轮询一次
                        let attempts = 0;
                        let taskCompleted = false;
                        
                        while (attempts < maxAttempts && !taskCompleted && !this.isCancelling) {
                            await new Promise(resolve => setTimeout(resolve, pollInterval));
                            attempts++;
                            
                            try {
                                const statusResult = await apiFetch(`/api/pdf/task-status/${taskId}`, {
                                    signal: this.currentAbortController.signal
                                });
                                
                                if (statusResult.success) {
                                    const taskStatus = statusResult.status;
                                    const progress = statusResult.progress || 0;
                                    
                                    if (taskStatus === 'completed') {
                                        // 任务完成
                                        record.status = 'generated';
                                        record.pdfPath = statusResult.pdf_path || null;
                                        taskCompleted = true;
                                        successCount++;
                                        if (statusResult.has_warning) {
                                            warningOrders.add(record.orderNo);
                                        }
                                        this.updateGenerateProgress(i + 1, selectedPendingRecords.length, record.orderNo, 'completed', 'PDF生成完成');
                                    } else if (taskStatus === 'failed') {
                                        // 任务失败
                                        record.status = 'pending';
                                        taskCompleted = true;
                                        failCount++;
                                        failedOrders.push(record.orderNo);
                                        this.updateGenerateProgress(i + 1, selectedPendingRecords.length, record.orderNo, 'failed', statusResult.error_message || 'PDF生成失败');
                                    } else if (taskStatus === 'processing') {
                                        // 仍在处理中
                                        record.status = 'generating';
                                        const progressText = statusResult.message || `正在生成PDF... (${progress}%)`;
                                        this.updateGenerateProgress(i, selectedPendingRecords.length, record.orderNo, 'processing', progressText);
                                    } else if (taskStatus === 'pending') {
                                        this.updateGenerateProgress(i, selectedPendingRecords.length, record.orderNo, 'processing', '任务等待中...');
                                    }
                                }
                            } catch (statusError) {
                                if (statusError.name === 'AbortError' || this.isCancelling) {
                                    throw statusError;
                                }
                                console.error('查询任务状态失败:', statusError);
                                // 继续轮询，不中断
                                if (attempts % 5 === 0) {
                                    this.updateGenerateProgress(i, selectedPendingRecords.length, record.orderNo, 'processing', '正在查询任务状态...');
                                }
                            }
                        }
                        
                        if (!taskCompleted && !this.isCancelling) {
                            // 超时，但可能已经生成
                            record.status = 'pending';
                            failCount++;
                            failedOrders.push(record.orderNo);
                            this.updateGenerateProgress(i + 1, selectedPendingRecords.length, record.orderNo, 'failed', '生成超时');
                        }
                    } catch (e) {
                        if (e.name === 'AbortError' || this.isCancelling) {
                            console.log('生成被取消');
                            this.hideGenerateProgress();
                            alert(`生成已取消。\n已生成: ${successCount} 个`);
                            
                            if (this.isSearching) {
                                await this.executeSearch();
                            } else {
                                await this.loadOrdersFromAPI(this.currentPage);
                            }
                            return;
                        }
                        console.error('生成失败:', e);
                        failCount++;
                        failedOrders.push(record.orderNo);
                        this.updateGenerateProgress(i + 1, selectedPendingRecords.length, record.orderNo, 'failed');
                    }
                    if (i < selectedPendingRecords.length - 1) await this.delay(200);
                }

                this.updateGenerateProgress(selectedPendingRecords.length, selectedPendingRecords.length, 'ALL', 'completed');
                await this.delay(300);
                this.hideGenerateProgress();

                if (this.isSearching) {
                    await this.executeSearch();
                } else {
                    await this.loadOrdersFromAPI(this.currentPage);
                }

                const warningList = Array.from(warningOrders);
                const warningText = warningList.length > 0
                    ? `\n存在空數據的訂單: ${warningList.join('、')}`
                    : '';
                if (failCount === 0) {
                    alert(`批量生成完成！成功生成 ${successCount} 個PDF。${warningText}`);
                } else {
                    alert(`批量生成結束！\n成功: ${successCount} 個\n失敗: ${failCount} 個\n失敗的訂單: ${failedOrders.join(', ')}${warningText}`);
                }

                this.clearSelection();
            } catch (error) {
                if (error.name === 'AbortError' || this.isCancelling) {
                    console.log('生成被取消');
                    this.hideGenerateProgress();
                    return;
                }
                console.error('批量生成失败:', error);
                this.hideGenerateProgress();
                alert('批量生成失败，请重试！');
            } finally {
                this.isCancelling = false;
                this.currentAbortController = null;
            }
        },

        async batchRegenerate() {
            if (!this.hasSelectedGeneratedRecords) {
                alert('请选择至少一条已生成的记录！');
                return;
            }

            // 只处理已生成的记录
            const currentSelected = this.currentSelectedRecords;
            const selectedGeneratedRecords = currentSelected
                .map(id => this.records.find(r => r.id === id))
                .filter(record => record && (record.status === 'generated' || record.status === 'pending'));

            if (selectedGeneratedRecords.length === 0) {
                alert('没有可重新生成的记录！请选择状态为"已生成"的记录。');
                return;
            }

            const confirmMessage = `确定要批量重新生成 ${selectedGeneratedRecords.length} 个订单的PDF吗？\n\n注意：这将覆盖现有的PDF文件。\n\n选中的记录：\n${selectedGeneratedRecords.slice(0, 5).map(r => `- ${r.orderNo} (${r.orderDescription || ''})`).join('\n')}${selectedGeneratedRecords.length > 5 ? `\n... 还有 ${selectedGeneratedRecords.length - 5} 个` : ''}`;
            if (!confirm(confirmMessage)) return;

            this.isCancelling = false;
            this.currentAbortController = new AbortController();

            try {
                this.showGenerateProgress(selectedGeneratedRecords.length, true);

                let successCount = 0;
                let failCount = 0;
                const failedOrders = [];
                const warningOrders = new Set();

                for (let i = 0; i < selectedGeneratedRecords.length; i++) {
                    if (this.isCancelling) {
                        console.log('用户取消了批量重新生成');
                        this.hideGenerateProgress();
                        alert(`重新生成已取消。\n已重新生成: ${successCount} 个\n失败: ${failCount} 个`);
                        
                        if (this.isSearching) {
                            await this.executeSearch();
                        } else {
                            await this.loadOrdersFromAPI(this.currentPage);
                        }
                        return;
                    }

                    const record = selectedGeneratedRecords[i];
                    record.status = 'generating';
                    // 更新进度：显示正在处理
                    this.updateGenerateProgress(i, selectedGeneratedRecords.length, record.orderNo, 'processing', '', true);

                    try {
                        // 提交重新生成任务
                        const result = await apiFetch('/api/pdf/generate', {
                            method: 'POST',
                            body: JSON.stringify({ order_no: record.orderNo }),
                            signal: this.currentAbortController.signal
                        });

                        if (!result.success || !result.task_id) {
                            throw new Error(result.error || '创建PDF生成任务失败');
                        }
                        
                        const taskId = result.task_id;
                        this.updateGenerateProgress(i, selectedGeneratedRecords.length, record.orderNo, 'processing', '任务已提交，等待处理...', true);
                        
                        // 轮询任务状态，直到完成或失败
                        const maxAttempts = 120; // 最多轮询120次（4分钟）
                        const pollInterval = 2000; // 每2秒轮询一次
                        let attempts = 0;
                        let taskCompleted = false;
                        
                        while (attempts < maxAttempts && !taskCompleted && !this.isCancelling) {
                            await new Promise(resolve => setTimeout(resolve, pollInterval));
                            attempts++;
                            
                            try {
                                const statusResult = await apiFetch(`/api/pdf/task-status/${taskId}`, {
                                    signal: this.currentAbortController.signal
                                });
                                
                                if (statusResult.success) {
                                    const taskStatus = statusResult.status;
                                    const progress = statusResult.progress || 0;
                                    
                                    if (taskStatus === 'completed') {
                                        // 任务完成
                                        record.status = 'generated';
                                        record.pdfPath = statusResult.pdf_path || null;
                                        taskCompleted = true;
                                        successCount++;
                                        if (statusResult.has_warning) {
                                            warningOrders.add(record.orderNo);
                                        }
                                        this.updateGenerateProgress(i + 1, selectedGeneratedRecords.length, record.orderNo, 'completed', 'PDF重新生成完成', true);
                                    } else if (taskStatus === 'failed') {
                                        // 任务失败
                                        record.status = 'pending';
                                        taskCompleted = true;
                                        failCount++;
                                        failedOrders.push(record.orderNo);
                                        this.updateGenerateProgress(i + 1, selectedGeneratedRecords.length, record.orderNo, 'failed', statusResult.error_message || 'PDF重新生成失败', true);
                                    } else if (taskStatus === 'processing') {
                                        // 仍在处理中
                                        record.status = 'generating';
                                        const progressText = statusResult.message || `正在重新生成PDF... (${progress}%)`;
                                        this.updateGenerateProgress(i, selectedGeneratedRecords.length, record.orderNo, 'processing', progressText, true);
                                    } else if (taskStatus === 'pending') {
                                        this.updateGenerateProgress(i, selectedGeneratedRecords.length, record.orderNo, 'processing', '任务等待中...', true);
                                    }
                                }
                            } catch (statusError) {
                                if (statusError.name === 'AbortError' || this.isCancelling) {
                                    throw statusError;
                                }
                                console.error('查询任务状态失败:', statusError);
                                // 继续轮询，不中断
                                if (attempts % 5 === 0) {
                                    this.updateGenerateProgress(i, selectedGeneratedRecords.length, record.orderNo, 'processing', '正在查询任务状态...', true);
                                }
                            }
                        }
                        
                        if (!taskCompleted && !this.isCancelling) {
                            // 超时，但可能已经生成
                            record.status = 'pending';
                            failCount++;
                            failedOrders.push(record.orderNo);
                            this.updateGenerateProgress(i + 1, selectedGeneratedRecords.length, record.orderNo, 'failed', '重新生成超时', true);
                        }
                    } catch (error) {
                        if (error.name === 'AbortError' || this.isCancelling) {
                            throw error;
                        }
                        failCount++;
                        failedOrders.push(record.orderNo);
                        record.status = 'pending';
                        // 更新进度：显示失败
                        this.updateGenerateProgress(i + 1, selectedGeneratedRecords.length, record.orderNo, 'failed', error.message || '重新生成失败', true);
                        console.error(`重新生成 Order ${record.orderNo} 失败:`, error);
                    }

                    // 添加延迟，避免请求过快
                    if (i < selectedGeneratedRecords.length - 1) {
                        await this.delay(200);
                    }
                }

                // 显示最终完成状态
                this.updateGenerateProgress(selectedGeneratedRecords.length, selectedGeneratedRecords.length, 'ALL', 'completed', true);
                await this.delay(300);
                this.hideGenerateProgress();

                // 刷新数据
                if (this.isSearching) {
                    await this.executeSearch();
                } else {
                    await this.loadOrdersFromAPI(this.currentPage);
                }

                const warningList = Array.from(warningOrders);
                const warningText = warningList.length > 0
                    ? `\n存在空數據的訂單: ${warningList.join('、')}`
                    : '';
                if (failCount === 0) {
                    alert(`批量重新生成完成！成功重新生成 ${successCount} 個PDF。${warningText}`);
                } else {
                    alert(`批量重新生成結束！\n成功: ${successCount} 個\n失敗: ${failCount} 個\n失敗的訂單: ${failedOrders.join(', ')}${warningText}`);
                }

                this.clearSelection();
            } catch (error) {
                if (error.name === 'AbortError' || this.isCancelling) {
                    console.log('重新生成被取消');
                    this.hideGenerateProgress();
                    return;
                }
                console.error('批量重新生成失败:', error);
                this.hideGenerateProgress();
                alert('批量重新生成失败，请重试！');
            } finally {
                this.isCancelling = false;
                this.currentAbortController = null;
            }
        },

        showGenerateProgress(total, isRegenerate = false) {
            const title = isRegenerate ? '批量重新生成中...' : '批量生成中...';
            const progressHtml = `
                <div id="generate-progress" class="download-progress-overlay">
                    <div class="download-progress-content">
                        <h3>${title}</h3>
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: 0%"></div>
                        </div>
                        <div class="progress-text">准备中......</div>
                        <div class="progress-details"></div>
                        <div class="progress-actions">
                            <button class="stop-btn" @click="stopGenerate">取消生成</button>
                        </div>
                    </div>
                </div>
            `;
            document.body.insertAdjacentHTML('beforeend', progressHtml);
            const stopBtn = document.querySelector('#generate-progress .stop-btn');
            if (stopBtn) {
                stopBtn.addEventListener('click', () => this.stopGenerate());
            }
        },

        updateGenerateProgress(current, total, currentRecord, status = 'processing', statusMessage = '', isRegenerate = false) {
            const overlay = document.getElementById('generate-progress') || document.getElementById('download-progress');
            const progressFill = overlay ? overlay.querySelector('.progress-fill') : null;
            const progressText = overlay ? overlay.querySelector('.progress-text') : null;
            const progressDetails = overlay ? overlay.querySelector('.progress-details') : null;
            if (progressFill && progressText && progressDetails) {
                const safeCurrent = Math.max(0, Math.min(current, total));
                let percentage = 0;
                if (total > 0) {
                    percentage = (safeCurrent / total) * 100;
                    if (safeCurrent === total) percentage = 100;
                }
                progressFill.style.width = `${percentage}%`;
                if (percentage === 100) progressFill.classList.add('complete');
                
                // 更新状态消息
                if (statusMessage) {
                    progressDetails.textContent = `当前: Order ${currentRecord} - ${statusMessage}`;
                } else {
                    const statusText = status === 'completed' ? '完成' : status === 'failed' ? '失败' : status === 'processing' ? '处理中' : '等待中';
                    progressDetails.textContent = `当前: Order ${currentRecord} - ${statusText}`;
                }
                
                const actionText = isRegenerate ? '重新生成' : '生成';
                
                if (status === 'processing') {
                    progressText.textContent = `正在${actionText} ${safeCurrent + 1}/${total}`;
                    progressDetails.textContent = `当前订单: ${currentRecord}`;
                } else if (status === 'completed') {
                    progressText.textContent = `已${actionText} ${safeCurrent}/${total}`;
                    progressDetails.textContent = safeCurrent === total ? `全部完成` : `完成: ${currentRecord}`;
                } else if (status === 'failed') {
                    progressText.textContent = `已处理 ${safeCurrent}/${total} (失败)`;
                    progressDetails.textContent = `失败: ${currentRecord}`;
                }
            }
        },

        hideGenerateProgress() {
            const overlay = document.getElementById('generate-progress');
            if (overlay) overlay.remove();
        },

        stopDownload() {
            this.isCancelling = true;
            if (this.currentAbortController) {
                this.currentAbortController.abort();
            }
            console.log('停止下载请求已发送');
        },

        stopGenerate() {
            this.isCancelling = true;
            if (this.currentAbortController) {
                this.currentAbortController.abort();
            }
            console.log('停止生成请求已发送');
        },
//将搜索区域和批量操作区域固定在页面顶部      
        setupStickyPositions() {
            // 使用 nextTick 确保 DOM 已渲染
            this.$nextTick(() => {
                const contentEl = document.querySelector('.content');
                const searchSection = document.querySelector('.search-section');
                const batchActions = document.querySelector('.batch-actions');
                const header = document.querySelector('.header');
                const sidebar = document.querySelector('.sidebar');

                if (!searchSection) return;

                let searchSectionOriginalTop = 0;
                let batchActionsOriginalTop = 0;
                let searchSectionOriginalWidth = 0;
                let batchActionsOriginalWidth = 0;
                let searchSectionOriginalLeft = 0;
                let batchActionsOriginalLeft = 0;
                let isSearchFixed = false;
                let isBatchFixed = false;
                let searchPlaceholder = null;
                let batchPlaceholder = null;

                // 获取滚动位置（兼容 window 与 .content）
                const getScrollTop = () => {
                    if (contentEl) {
                        const style = getComputedStyle(contentEl);
                        // 检查 overflow-y 或 overflow 是否为 auto/scroll
                        const overflowY = style.overflowY || style.overflow;
                        if (overflowY === 'auto' || overflowY === 'scroll') {
                            return contentEl.scrollTop;
                        }
                    }
                    return window.pageYOffset || document.documentElement.scrollTop || document.body.scrollTop || 0;
                };

                const computeDims = () => {
                    const headerHeight = header ? header.offsetHeight : 0;
                    const contentRect = contentEl ? contentEl.getBoundingClientRect() : document.body.getBoundingClientRect();
                    const sidebarWidth = sidebar ? sidebar.offsetWidth : 260;
                    return { headerHeight, contentRect, sidebarWidth };
                };

                const measureOriginalTopsOnce = () => {
                    // 只记录一次初始 top、width 和 left（更稳妥）
                    if (searchSectionOriginalTop === 0 && searchSection) {
                        // 相对滚动容器的测量
                        // 如果 contentEl 是滚动容器，使用 offsetTop
                        // 否则需要计算相对于文档的位置
                        if (contentEl && getComputedStyle(contentEl).overflowY !== 'visible') {
                            searchSectionOriginalTop = searchSection.offsetTop;
                        } else {
                            // 对于 window 滚动，需要计算相对于文档的位置
                            const rect = searchSection.getBoundingClientRect();
                            searchSectionOriginalTop = rect.top + (window.pageYOffset || document.documentElement.scrollTop);
                        }
                        // 记录原始宽度和 left 位置
                        searchSectionOriginalWidth = searchSection.offsetWidth;
                        const rect = searchSection.getBoundingClientRect();
                        searchSectionOriginalLeft = rect.left;
                        console.log('[Sticky] 搜索区域原始位置:', searchSectionOriginalTop, '原始宽度:', searchSectionOriginalWidth, '原始left:', searchSectionOriginalLeft);
                    }
                    if (batchActions && batchActionsOriginalTop === 0) {
                        if (contentEl && getComputedStyle(contentEl).overflowY !== 'visible') {
                            batchActionsOriginalTop = batchActions.offsetTop;
                        } else {
                            const rect = batchActions.getBoundingClientRect();
                            batchActionsOriginalTop = rect.top + (window.pageYOffset || document.documentElement.scrollTop);
                        }
                        // 记录原始宽度和 left 位置
                        batchActionsOriginalWidth = batchActions.offsetWidth;
                        const rect = batchActions.getBoundingClientRect();
                        batchActionsOriginalLeft = rect.left;
                        console.log('[Sticky] 批量操作区域原始位置:', batchActionsOriginalTop, '原始宽度:', batchActionsOriginalWidth, '原始left:', batchActionsOriginalLeft);
                    }
                };

                const setSearchFixed = ({ headerHeight, contentRect, sidebarWidth }) => {
                    if (!searchPlaceholder) {
                        searchPlaceholder = document.createElement('div');
                        searchPlaceholder.style.height = `${searchSection.offsetHeight}px`;
                        searchPlaceholder.style.marginBottom = window.getComputedStyle(searchSection).marginBottom;
                        searchSection.parentNode.insertBefore(searchPlaceholder, searchSection);
                    }
                    // 使用原始宽度和 left 位置，保持位置和宽度不变
                    const fixedWidth = searchSectionOriginalWidth > 0 ? searchSectionOriginalWidth : searchSection.offsetWidth;
                    const fixedLeft = searchSectionOriginalLeft > 0 ? searchSectionOriginalLeft : searchSection.getBoundingClientRect().left;
                    searchSection.style.position = 'fixed';
                    searchSection.style.top = `${headerHeight}px`;
                    searchSection.style.left = `${fixedLeft}px`;
                    searchSection.style.width = `${fixedWidth}px`;
                    searchSection.style.zIndex = '150';
                    searchSection.style.marginLeft = '0';
                    searchSection.style.marginRight = '0';
                    isSearchFixed = true;
                };

                const unsetSearchFixed = () => {
                    searchSection.style.position = 'sticky';
                    searchSection.style.top = '0';
                    searchSection.style.left = '';
                    searchSection.style.width = '';
                    searchSection.style.marginLeft = '';
                    searchSection.style.marginRight = '';
                    if (searchPlaceholder) {
                        searchPlaceholder.remove();
                        searchPlaceholder = null;
                    }
                    isSearchFixed = false;
                    // 不再每次归零 originalTop，改为只测一次更稳
                    // searchSectionOriginalTop = 0;
                };

                const setBatchFixed = ({ headerHeight, contentRect, sidebarWidth }) => {
                    if (!batchActions) return;
                    if (!batchPlaceholder) {
                        batchPlaceholder = document.createElement('div');
                        batchPlaceholder.style.height = `${batchActions.offsetHeight}px`;
                        batchPlaceholder.style.marginBottom = window.getComputedStyle(batchActions).marginBottom;
                        batchActions.parentNode.insertBefore(batchPlaceholder, batchActions);
                    }
                    const searchHeight = isSearchFixed ? searchSection.offsetHeight : 0;
                    const searchMarginBottom = isSearchFixed ? (parseInt(window.getComputedStyle(searchSection).marginBottom, 10) || 24) : 0;
                    // 使用原始宽度和 left 位置，保持位置和宽度不变
                    const fixedWidth = batchActionsOriginalWidth > 0 ? batchActionsOriginalWidth : batchActions.offsetWidth;
                    const fixedLeft = batchActionsOriginalLeft > 0 ? batchActionsOriginalLeft : batchActions.getBoundingClientRect().left;
                    batchActions.style.position = 'fixed';
                    batchActions.style.top = `${headerHeight + searchHeight + searchMarginBottom}px`;
                    batchActions.style.left = `${fixedLeft}px`;
                    batchActions.style.width = `${fixedWidth}px`;
                    batchActions.style.zIndex = '200';
                    batchActions.style.marginLeft = '0';
                    batchActions.style.marginRight = '0';
                    isBatchFixed = true;
                };

                const unsetBatchFixed = () => {
                    if (!batchActions) return;
                    batchActions.style.position = 'sticky';
                    batchActions.style.top = '';
                    batchActions.style.left = '';
                    batchActions.style.width = '';
                    batchActions.style.marginLeft = '';
                    batchActions.style.marginRight = '';
                    if (batchPlaceholder) {
                        batchPlaceholder.remove();
                        batchPlaceholder = null;
                    }
                    isBatchFixed = false;
                    // 同上，保持原始 top 不再频繁归零
                    // batchActionsOriginalTop = 0;
                };

                let rafId = null;
                const updatePositions = () => {
                    // 节流：取消前一个帧
                    if (rafId) cancelAnimationFrame(rafId);
                    rafId = requestAnimationFrame(() => {
                        if (!searchSection) return;
                        measureOriginalTopsOnce();

                        const scrollTop = getScrollTop();
                        const { headerHeight, contentRect, sidebarWidth } = computeDims();
                        
                        // 调试日志（仅在开发时使用，生产环境可移除）
                        if (scrollTop > 0) {
                            console.log('[Sticky] 滚动位置:', scrollTop, '搜索区域原始位置:', searchSectionOriginalTop);
                        }

                        // 搜索区固定与还原
                        if (scrollTop > searchSectionOriginalTop - 10) {
                            if (!isSearchFixed) {
                                setSearchFixed({ headerHeight, contentRect, sidebarWidth });
                            } else {
                                // 实时更新（保持宽度和 left 位置不变）
                                const fixedWidth = searchSectionOriginalWidth > 0 ? searchSectionOriginalWidth : searchSection.offsetWidth;
                                const fixedLeft = searchSectionOriginalLeft > 0 ? searchSectionOriginalLeft : searchSection.getBoundingClientRect().left;
                                searchSection.style.width = `${fixedWidth}px`;
                                searchSection.style.left = `${fixedLeft}px`;
                            }
                        } else if (isSearchFixed) {
                            unsetSearchFixed();
                        }

                        // 批量区固定与还原（需有选中记录）
                        const currentSelected = this.currentSelectedRecords;
                        if (batchActions && currentSelected && currentSelected.length > 0) {
                            if (scrollTop > batchActionsOriginalTop - 10) {
                                if (!isBatchFixed) {
                                    setBatchFixed({ headerHeight, contentRect, sidebarWidth });
                                } else {
                                    const searchHeight = isSearchFixed ? searchSection.offsetHeight : 0;
                                    const searchMarginBottom = isSearchFixed ? (parseInt(window.getComputedStyle(searchSection).marginBottom, 10) || 24) : 0;
                                    // 保持宽度和 left 位置不变
                                    const fixedWidth = batchActionsOriginalWidth > 0 ? batchActionsOriginalWidth : batchActions.offsetWidth;
                                    const fixedLeft = batchActionsOriginalLeft > 0 ? batchActionsOriginalLeft : batchActions.getBoundingClientRect().left;
                                    batchActions.style.top = `${headerHeight + searchHeight + searchMarginBottom}px`;
                                    batchActions.style.width = `${fixedWidth}px`;
                                    batchActions.style.left = `${fixedLeft}px`;
                                }
                            } else if (isBatchFixed) {
                                unsetBatchFixed();
                            }
                        } else if (isBatchFixed) {
                            // 没有选中记录但仍 fixed：立即恢复
                            unsetBatchFixed();
                        }
                    });
                };

                // 事件绑定
                const onScroll = updatePositions;
                const onResize = updatePositions;

                // 确定滚动容器
                let scrollContainer = null;
                if (contentEl) {
                    const style = getComputedStyle(contentEl);
                    const overflowY = style.overflowY || style.overflow;
                    if (overflowY === 'auto' || overflowY === 'scroll') {
                        scrollContainer = contentEl;
                    }
                }
                
                if (scrollContainer) {
                    scrollContainer.addEventListener('scroll', onScroll, { passive: true });
                    console.log('[Sticky] 绑定滚动事件到 .content 容器');
                } else {
                    window.addEventListener('scroll', onScroll, { passive: true });
                    console.log('[Sticky] 绑定滚动事件到 window');
                }
                window.addEventListener('resize', onResize);
                
                // 监听侧栏宽度变化（如果侧栏有折叠功能）
                if (sidebar) {
                    const sidebarObserver = new MutationObserver(() => {
                        // 侧栏宽度变化时重新计算位置
                        updatePositions();
                    });
                    sidebarObserver.observe(sidebar, {
                        attributes: true,
                        attributeFilter: ['style', 'class'],
                        childList: false,
                        subtree: false
                    });
                }

                // 初始执行一次
                updatePositions();

                // 保存清理函数，在 beforeUnmount 中调用
                this._stickyCleanup = () => {
                    const style = contentEl ? getComputedStyle(contentEl) : null;
                    const overflowY = style ? (style.overflowY || style.overflow) : null;
                    if (contentEl && (overflowY === 'auto' || overflowY === 'scroll')) {
                        contentEl.removeEventListener('scroll', onScroll);
                    } else {
                        window.removeEventListener('scroll', onScroll);
                    }
                    window.removeEventListener('resize', onResize);
                    if (rafId) cancelAnimationFrame(rafId);
                };
            });
        }

    },
    beforeUnmount() {
        // 清理事件监听器
        if (this._enterKeyHandler) {
            document.removeEventListener('keydown', this._enterKeyHandler);
        }
        
        // 清理 sticky 相关的事件监听器
        if (this._stickyCleanup) {
            this._stickyCleanup();
        }
        
        // 清理更新数据轮询
        if (this.updateCheckInterval) {
            clearInterval(this.updateCheckInterval);
            this.updateCheckInterval = null;
        }
    }
}).mount('#app');

