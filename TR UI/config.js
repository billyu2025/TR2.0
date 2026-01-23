// TR Report System 前端配置文件
// 此文件在构建时或运行时会被替换为实际配置
// 版本: 2026-01-13 (强制刷新缓存)

// API 基础 URL
// 自动检测当前访问地址，支持内网、外网和本地文件访问
(function() {
    const protocol = window.location.protocol;
    const hostname = window.location.hostname;
    const port = window.location.port;
    
    // 检测是否是 file:// 协议（直接打开 HTML 文件）
    if (protocol === 'file:') {
        // 本地文件访问，直接使用 localhost:5000
        window.API_BASE_URL = 'http://localhost:5000';
    }
    // 本地开发环境（localhost 或 127.0.0.1），且端口是 5000，直接访问后端
    else if ((hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '') && port === '5000') {
        window.API_BASE_URL = 'http://localhost:5000';
    }
    // 其他所有情况（包括内网、外网通过 Nginx 访问），都使用相对路径
    // 这样 Nginx 会自动将 /api 请求转发到后端
    else {
        window.API_BASE_URL = '/api';
    }
    
    // 强制设置，防止被其他脚本覆盖
    Object.defineProperty(window, 'API_BASE_URL', {
        value: window.API_BASE_URL,
        writable: false,
        configurable: false
    });
    
    // 调试信息
    console.log('API_BASE_URL:', window.API_BASE_URL, 'protocol:', protocol, 'hostname:', hostname, 'port:', port);
})();

// 应用配置
window.APP_CONFIG = {
    API_BASE_URL: window.API_BASE_URL,
    // 可以添加其他配置项
    // VERSION: '1.0.0',
    // TIMEOUT: 30000,
};

