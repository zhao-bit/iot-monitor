/**
 * ============================================
 * 物联网智能监控系统 - 主入口文件
 * 功能：路由管理、导航切换、移动端菜单
 * ============================================
 */

// 等待DOM加载完成
document.addEventListener('DOMContentLoaded', function() {
    console.log('智能监控系统初始化...');
    
    // 初始化导航系统
    initNavigation();
    
    // 初始化移动端菜单
    initMobileMenu();
    
    console.log('系统初始化完成！');
});

/**
 * 初始化导航系统
 * 功能：处理板块之间的切换，更新URL哈希
 */
function initNavigation() {
    // 获取所有导航项和板块
    const navItems = document.querySelectorAll('.nav-item');
    const sections = document.querySelectorAll('.section');
    
    // 为每个导航项添加点击事件
    navItems.forEach(item => {
        item.addEventListener('click', function(e) {
            e.preventDefault();
            
            // 获取目标板块ID（从data-section属性）
            const targetSection = this.getAttribute('data-section');
            
            // 切换板块显示
            switchSection(targetSection);
            
            // 更新导航状态（高亮当前选中的导航项）
            updateNavActive(this);
            
            // 移动端：点击后关闭菜单
            if (window.innerWidth <= 768) {
                const navMenu = document.getElementById('navMenu');
                navMenu.classList.remove('active');
                // 恢复汉堡菜单图标
                const menuToggle = document.getElementById('mobileMenuToggle');
                const icon = menuToggle.querySelector('i');
                icon.classList.remove('fa-times');
                icon.classList.add('fa-bars');
            }
        });
    });
    
    // 处理URL哈希（支持直接访问某个板块，如：index.html#image-recognition）
    if (window.location.hash) {
        const hash = window.location.hash.substring(1); // 去掉#号
        switchSection(hash);
        const activeNav = document.querySelector(`[data-section="${hash}"]`);
        if (activeNav) {
            updateNavActive(activeNav);
        }
    }
}

/**
 * 切换板块显示
 * @param {string} sectionId - 板块ID（如：'image-recognition'）
 */
function switchSection(sectionId) {
    // 隐藏所有板块
    const sections = document.querySelectorAll('.section');
    sections.forEach(section => {
        section.classList.remove('active');
    });
    
    // 显示目标板块
    const targetSection = document.getElementById(sectionId);
    if (targetSection) {
        targetSection.classList.add('active');
        // 更新URL哈希（不触发页面跳转）
        window.history.replaceState(null, null, `#${sectionId}`);
        
        // 滚动到顶部（平滑滚动）
        window.scrollTo({
            top: 0,
            behavior: 'smooth'
        });
    } else {
        console.warn(`板块 ${sectionId} 不存在`);
        // 如果板块不存在，显示欢迎页面
        const welcomeSection = document.getElementById('welcome');
        if (welcomeSection) {
            welcomeSection.classList.add('active');
        }
    }
}

/**
 * 更新导航激活状态
 * @param {HTMLElement} activeItem - 当前激活的导航项元素
 */
function updateNavActive(activeItem) {
    // 移除所有导航项的激活状态
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
        item.classList.remove('active');
    });
    
    // 添加当前导航项的激活状态
    activeItem.classList.add('active');
}

/**
 * 初始化移动端菜单（汉堡菜单）
 * 功能：在移动设备上显示/隐藏导航菜单
 */
function initMobileMenu() {
    const menuToggle = document.getElementById('mobileMenuToggle');
    const navMenu = document.getElementById('navMenu');
    
    if (menuToggle && navMenu) {
        // 点击汉堡菜单按钮
        menuToggle.addEventListener('click', function(e) {
            e.stopPropagation(); // 阻止事件冒泡
            
            // 切换菜单显示状态
            navMenu.classList.toggle('active');
            
            // 切换图标（汉堡菜单 ↔ 关闭图标）
            const icon = this.querySelector('i');
            if (navMenu.classList.contains('active')) {
                icon.classList.remove('fa-bars');
                icon.classList.add('fa-times');
            } else {
                icon.classList.remove('fa-times');
                icon.classList.add('fa-bars');
            }
        });
        
        // 点击外部区域关闭菜单
        document.addEventListener('click', function(e) {
            // 如果点击的不是菜单和按钮，则关闭菜单
            if (!navMenu.contains(e.target) && !menuToggle.contains(e.target)) {
                navMenu.classList.remove('active');
                const icon = menuToggle.querySelector('i');
                icon.classList.remove('fa-times');
                icon.classList.add('fa-bars');
            }
        });
        
        // 窗口大小改变时，如果切换到桌面端，自动关闭移动菜单
        window.addEventListener('resize', function() {
            if (window.innerWidth > 768) {
                navMenu.classList.remove('active');
                const icon = menuToggle.querySelector('i');
                icon.classList.remove('fa-times');
                icon.classList.add('fa-bars');
            }
        });
    }
}

/**
 * 工具函数：显示提示消息（可选，后续可扩展）
 * @param {string} message - 提示消息
 * @param {string} type - 消息类型：success, error, warning, info
 */
function showMessage(message, type = 'info') {
    console.log(`[${type.toUpperCase()}] ${message}`);
    // 后续可以在这里添加UI提示功能
}
