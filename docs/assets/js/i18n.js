// HUNTX browser i18n runtime. English source strings remain the canonical keys.
export const SUPPORTED_LOCALES = Object.freeze(["en", "fa", "zh-CN", "ru"]);

export const TRANSLATIONS = Object.freeze({
  fa: {
    // Navigation & Primary Headers
    "GATHERX TELEMETRY": "تله‌متری GATHERX",
    "NODE TELEMETRY": "تله‌متری گره‌ها",
    "PIPELINE ONLINE": "خط پردازش آنلاین",
    "IP Scanner": "اسکنر IP",
    "Sub Builder": "سازنده اشتراک",
    "Decoder": "رمزگشا",
    "3D Topology": "توپولوژی سه‌بعدی",
    "Radar": "رادار",
    "Telemetry Radar": "رادار تله‌متری",
    "Proxies": "پروکسی‌ها",
    "Live Proxies": "پروکسی‌های زنده",
    "Studio": "استودیو",
    "Protocol Studio": "استودیوی پروتکل",
    "Artifacts": "خروجی‌ها",
    "Artifacts & Feeds": "خروجی‌ها و اشتراک‌ها",
    "Architecture": "معماری سامانه",

    // Hero & Overview
    "Zero-Budget Sovereign Proxy Ingestion": "گردآوری مستقل پروکسی بدون هزینه",
    "Automated Multi-Source Collector": "گردآوری خودکار و چندمنبعی پروکسی",
    "Proxy Telemetry &": "تله‌متری پروکسی و",
    "Cyber Intelligence": "دیده‌بانی و امنیت سایبری",
    "Node Diagnostics": "تشخیص سلامت و عملکرد",
    "Active Nodes": "گره‌های فعال",
    "Ingest Sources": "منابع ورودی",
    "Published Files": "فایل‌های منتشرشده",
    "Avg Latency": "میانگین تأخیر",
    "Channels": "کانال‌ها",
    "Unmeasured": "اندازه‌گیری‌نشده",
    "Copy Production Feed": "کپی لینک اشتراک اصلی",
    "Browse Verified Artifacts": "مشاهده فایل‌های تأییدشده",
    "Live Node Intelligence": "اطلاعات زنده گره‌ها",

    // UI Badges & Status Indicators
    "SYNCING": "در حال همگام‌سازی",
    "STUDIO": "استودیو",
    "RAW": "خام",
    "SAMPLE": "نمونه",
    "LIVE": "زنده",
    "Bundled snapshot": "نسخه محلی پیش‌فرض",
    "Live verified snapshot": "نسخه زنده و تأییدشده",
    "INTEGRITY CHECK FAILED": "خطای بررسی یکپارچگی داده",
    "NO LIVE PROBES": "بدون آزمایش زنده",
    "TAP HUB": "لمس مرکز",
    "Explore 3D Globe": "کاوش در کره سه‌بعدی",
    "Exit 3D Mode": "خروج از حالت سه‌بعدی",
    "INTERACTIVE 3D GEO-RADAR": "رادار جغرافیایی سه‌بعدی تعاملی",
    "CLICK HUB TO FILTER": "برای فیلتر روی مرکز کلیک کنید",
    "Telemetry Pipeline Synchronized & Verified": "خط تله‌متری همگام و تأییدشده",
    "Ingestion Pipeline Synchronized & Verified": "خط پردازش ورودی همگام و تأیید شد",
    "Live Carrier Latency & Ingress Matrix": "ماتریس زنده تأخیر اپراتور و ورودی",
    "Strategic Geo-Cluster Density": "تراکم راهبردی خوشه‌های جغرافیایی",
    "Geographic Node Distribution": "توزیع جغرافیایی گره‌ها",

    // Filters & Toolbar
    "Search": "جستجو",
    "All Protocols": "همه پروتکل‌ها",
    "All Countries": "همه کشورها",
    "All Regions": "همه مناطق",
    "Geo Location": "موقعیت جغرافیایی",
    "All Transports": "همه پروتکل‌های انتقال",
    "All Operators": "همه اپراتورها",
    "All Health Grades": "همه سطوح سلامت",
    "All Security Types": "همه انواع امنیت",
    "Telemetry Sorting": "مرتب‌سازی تله‌متری",
    "Fastest Latency": "کمترین تأخیر",
    "Top Health Score": "بالاترین امتیاز سلامت",
    "Name (A-Z)": "نام (الف-ی)",
    "Country (A-Z)": "کشور (الف-ی)",
    "Port (Low-High)": "پورت (کم به زیاد)",
    "Grid View": "نمای شبکه‌ای",
    "Table View": "نمای جدولی",
    "Feed View": "نمای خوراک",
    "Cards": "کارت‌ها",
    "Table": "جدول",
    "Raw Feed": "خوراک خام",
    "Filter name, IP, SNI...": "فیلتر بر اساس نام، آی‌پی، SNI...",
    "Search artifacts...": "جستجوی فایل‌ها و خروجی‌ها...",
    "Reset Filters": "بازنشانی فیلترها",
    "Reset All Filters": "بازنشانی همه فیلترها",
    "Reset Artifact Filters": "بازنشانی فیلتر خروجی‌ها",
    "No artifacts match the current filter set": "هیچ خروجی با فیلترهای فعلی مطابقت ندارد",
    "No proxy endpoints match current dimensional filters": "هیچ پروکسی با فیلترهای فعلی مطابقت ندارد",

    // Common Actions
    "Protocol": "پروتکل",
    "Country": "کشور",
    "Region": "منطقه",
    "Transport": "پروتکل انتقال",
    "Security": "امنیت",
    "Latency": "تأخیر",
    "Copy": "کپی",
    "Copy URI": "کپی لینک",
    "Copy Node URI": "کپی نشانی گره",
    "Copy Output": "کپی خروجی",
    "Download": "دانلود",
    "Download File": "دانلود فایل",
    "Close": "بستن",
    "Cancel": "لغو",
    "Export": "خروجی",
    "Reset": "بازنشانی",
    "Start Scan": "شروع اسکن",
    "Published data updated": "داده‌های منتشرشده به‌روزرسانی شد",
    "Language": "زبان",
    "Toggle Theme": "تغییر پوسته",
    "Global Search": "جستجوی سراسری",
    "Status": "وضعیت",
    "Actions": "عملیات",
    "Action": "عملیات",
    "Operator / Carrier": "اپراتور شبکه / مخابرات",
    "Carrier": "اپراتور",
    "Server Address": "نشانی سرور",
    "Transport Layer": "لایه انتقال",
    "Security / TLS": "امنیت / TLS",
    "Health Grade": "رتبه سلامت",
    "Health": "سلامت",
    "Inspect Parameters": "بررسی پارامترها",
    "Search nodes, protocols, SNI, country...": "جستجوی گره، پروتکل، SNI، کشور...",

    // Modal & Quick Action Buttons
    "Open Clean IP Scanner": "اسکنر آی‌پی تمیز کلادفلر",
    "Open Subscription Builder": "باز کردن سازنده اشتراک",
    "Open Protocol Decoder": "باز کردن رمزگشای پروتکل",
    "GitHub Repository": "مخزن گیت‌هاب",
    "Sing-box Profile": "پروفایل Sing-box",
    "Xray Config": "کانفیگ Xray",
    "Cumulative JSON": "فایل JSON تجمیعی",
    "Sing-box JSON": "فایل JSON سینگ‌باکس",
    "Copy Plain URIs": "کپی لینک‌های ساده",
    "Copy Base64 Feed": "کپی اشتراک Base64",
    "Copy Unique URIs": "کپی لینک‌های یکتا",
    "Load Active Nodes": "بارگذاری گره‌های فعال",
    "Copy JSON": "کپی JSON",
    "Copy Sing-box": "کپی Sing-box",
    "Copy Clash": "کپی Clash",
    "Download SVG": "دانلود SVG",
    "Copy SVG": "کپی SVG",
    "Save SVG": "ذخیره SVG",
    "Copy Best IP": "کپی بهترین آی‌پی",
    "Copy All Clean": "کپی همه آی‌پی‌های تمیز",
    "Export CSV": "خروجی CSV",
    "Export JSON": "خروجی JSON",
    "Endpoint (Host:Port)": "نقطه اتصال (هاست:پورت)",
    "Transport & TLS": "انتقال و امنیت TLS",
    "Remark / Name": "نام / توضیحات",
    "Port": "پورت",
    "Credential / UUID": "شناسه کاربری / UUID",
    "SNI / ServerName": "نام سرور / SNI",
    "Transport Network": "شبکه انتقال",
    "Reality Public Key (pbk)": "کلید عمومی Reality (pbk)",
    "Short ID (sid)": "شناسه کوتاه (sid)",
    "gRPC ServiceName": "نام سرویس gRPC",
    "Sing-box Outbound Object:": "ساختار خروجی Sing-box:",
    "Sanitize Remarks": "پاکسازی نام‌ها",
    "Enrich Operators": "تکمیل اطلاعات اپراتورها",
    "Ingested": "ورودی",
    "Routing Profile Reference": "الگوی پروفایل مسیریابی",
    "Keyboard Navigation": "کلیدهای میانبر",
    "Color Preset:": "پوسته رنگی:",
    "Error Correction (ECC):": "تصحیح خطا (ECC):",
    "Content / Proxy URI to Encode:": "محتوا یا نشانی پروکسی برای رمزگذاری:",
    "Target IP": "آی‌پی مقصد",
    "Latency (RTT)": "تأخیر (RTT)",
    "Sample Count:": "تعداد نمونه:",

    // Protocol Studio & Deduplication
    "Universal Protocol Converter & Inspection Studio": "استودیوی تبدیل و تحلیل همه‌منظوره پروتکل",
    "Protocol Converter & Inspection Studio": "استودیوی تبدیل و تحلیل پروتکل",
    "Proxy Protocol Inspector": "تحلیل‌گر پروتکل پروکسی",
    "Protocol Inspector": "تحلیل‌گر پروتکل",
    "Universal Converter": "مبدل همه‌منظوره",
    "Bulk Deduplicator": "حذف گروهی موارد تکراری",
    "QR Code Studio": "استودیوی کد QR",
    "Source Proxy URIs / Base64 Subscription:": "نشانی‌های پروکسی / اشتراک Base64:",
    "Target Client / Engine Format": "فرمت کلاینت / هسته مقصد",
    "Convert All Nodes": "تبدیل همه گره‌ها",
    "Converted Output Result:": "نتیجه تبدیل:",
    "Run SHA-256 Deduplication": "حذف موارد تکراری با SHA-256",
    "Duplicates Purged": "موارد تکراری حذف‌شده",
    "Unique Nodes": "گره‌های یکتا",
    "Subscription Feeds & Client Configurations": "خوراک‌های اشتراک و پیکربندی کلاینت",
    "Pipeline Output & Artifacts Repository": "مخزن خروجی‌ها و بسته‌های تولیدی",

    // Cloudflare Clean IP Scanner
    "Cloudflare Clean IP Scanner": "اسکنر آی‌پی تمیز کلادفلر",
    "Target CIDR Subnet:": "زیرشبکه CIDR مقصد:",
    "Start Speedtest": "شروع آزمون سرعت",
    "Rescan Subnet": "اسکن دوباره زیرشبکه",
    "No scan performed yet.": "هنوز اسکنی انجام نشده است.",
    "Ready to scan. Select range and start speedtest.": "آماده اسکن. محدوده را انتخاب کرده و تست سرعت را آغاز کنید.",

    // Tooltips & Accessibility Labels
    "Toggle Light / Dark Theme (Press T)": "تغییر پوسته روشن / تاریک (کلید T)",
    "Open Clean IP Scanner (Press S)": "اسکنر آی‌پی تمیز کلادفلر (کلید S)",
    "Open Protocol Decoder (Press D)": "باز کردن رمزگشای پروتکل (کلید D)",
    "Open Interactive System Architecture": "مشاهده معماری تعاملی سامانه",
    "Grid Cards View (Press V)": "نمای کارتی (کلید V)",
    "Dense Data Table View (Press V)": "نمای جدولی فشرده (کلید V)",
    "Raw Text / Feed View": "نمای متن خام / خوراک",
    "Filter by Operator": "فیلتر بر اساس اپراتور",
    "Filter by Transport": "فیلتر بر اساس پروتکل انتقال",
    "Filter by Region": "فیلتر بر اساس منطقه",
    "Filter by Health Grade": "فیلتر بر اساس سطح سلامت",
    "Filter by Security": "فیلتر بر اساس امنیت",
    "Sort Order": "ترتیب مرتب‌سازی",
    "Copy Production Base64 Subscription URL": "کپی نشانی اشتراک Base64 اصلی",
    "Toggle Interactive 3D Mode": "تغییر حالت سه‌بعدی تعاملی",
    "Toggle Inline QR Code": "نمایش/پنهان‌سازی کد QR",
    "Inspect Protocol Parameters": "بررسی پارامترهای پروتکل",
    "Export Sing-box Outbound Snippet": "خروجی ساختار Sing-box",
    "Scan using v2rayNG, Sing-box, NekoBox, Hiddify, or Streisand": "اسکن با v2rayNG، Sing-box، NekoBox، Hiddify یا Streisand",
    "Scan with v2rayNG / Sing-box": "اسکن با v2rayNG / Sing-box",

    // 26 Localized Country Names
    "Germany": "آلمان",
    "Netherlands": "هلند",
    "United States": "ایالات متحده",
    "United Kingdom": "بریتانیا",
    "France": "فرانسه",
    "Finland": "فنلاند",
    "Singapore": "سنگاپور",
    "Japan": "ژاپن",
    "South Korea": "کره جنوبی",
    "Hong Kong": "هنگ‌کنگ",
    "Turkey": "ترکیه",
    "Sweden": "سوئد",
    "Switzerland": "سوئیس",
    "Canada": "کانادا",
    "Iran": "ایران",
    "Russia": "روسیه",
    "Australia": "استرالیا",
    "Brazil": "برزیل",
    "South Africa": "آفریقای جنوبی",
    "Italy": "ایتالیا",
    "Spain": "اسپانیا",
    "UAE": "امارات متحده عربی",
    "India": "هند",
    "Taiwan": "تایوان",
    "Ukraine": "اوکراین",
    "Ireland": "ایرلند"
  },
  "zh-CN": {
    // Navigation & Primary Headers
    "GATHERX TELEMETRY": "GATHERX 遥测",
    "NODE TELEMETRY": "节点遥测",
    "PIPELINE ONLINE": "流水线在线",
    "IP Scanner": "IP 扫描器",
    "Sub Builder": "订阅生成器",
    "Decoder": "解码器",
    "3D Topology": "三维拓扑",
    "Radar": "雷达",
    "Telemetry Radar": "遥测雷达",
    "Proxies": "代理",
    "Live Proxies": "实时代理",
    "Studio": "工作室",
    "Protocol Studio": "协议工作室",
    "Artifacts": "构建产物",
    "Artifacts & Feeds": "产物与订阅",
    "Architecture": "系统架构",

    // Hero & Overview
    "Zero-Budget Sovereign Proxy Ingestion": "零成本自主代理采集",
    "Automated Multi-Source Collector": "多源自动化代理采集器",
    "Proxy Telemetry &": "代理遥测与",
    "Cyber Intelligence": "网络威胁情报",
    "Node Diagnostics": "健康与性能诊断",
    "Active Nodes": "活跃节点",
    "Ingest Sources": "采集来源",
    "Published Files": "已发布文件",
    "Avg Latency": "平均延迟",
    "Channels": "频道",
    "Unmeasured": "未测量",
    "Copy Production Feed": "复制生产订阅",
    "Browse Verified Artifacts": "浏览已验证产物",
    "Live Node Intelligence": "实时节点情报",

    // UI Badges & Status Indicators
    "SYNCING": "同步中",
    "STUDIO": "工作室",
    "RAW": "原始",
    "SAMPLE": "示例",
    "LIVE": "实时",
    "Bundled snapshot": "内置快照",
    "Live verified snapshot": "实时已验证快照",
    "INTEGRITY CHECK FAILED": "完整性校验失败",
    "NO LIVE PROBES": "无实时探测",
    "TAP HUB": "点击枢纽",
    "Explore 3D Globe": "探索三维地球",
    "Exit 3D Mode": "退出三维模式",
    "INTERACTIVE 3D GEO-RADAR": "交互式三维地理雷达",
    "CLICK HUB TO FILTER": "点击枢纽进行筛选",
    "Telemetry Pipeline Synchronized & Verified": "遥测流水线已同步并验证",
    "Ingestion Pipeline Synchronized & Verified": "采集流水线已同步并验证",
    "Live Carrier Latency & Ingress Matrix": "实时运营商延迟与入口矩阵",
    "Strategic Geo-Cluster Density": "战略地理集群密度",
    "Geographic Node Distribution": "地理节点分布",

    // Filters & Toolbar
    "Search": "搜索",
    "All Protocols": "全部协议",
    "All Countries": "全部国家/地区",
    "All Regions": "全部地区",
    "Geo Location": "地理位置",
    "All Transports": "全部传输协议",
    "All Operators": "全部运营商",
    "All Health Grades": "全部健康等级",
    "All Security Types": "全部安全类型",
    "Telemetry Sorting": "遥测排序",
    "Fastest Latency": "最低延迟",
    "Top Health Score": "最佳健康评分",
    "Name (A-Z)": "名称 (A-Z)",
    "Country (A-Z)": "按国家/地区 (A-Z)",
    "Port (Low-High)": "端口 (从小到大)",
    "Grid View": "网格视图",
    "Table View": "表格视图",
    "Feed View": "信息流视图",
    "Cards": "卡片",
    "Table": "表格",
    "Raw Feed": "原始订阅",
    "Filter name, IP, SNI...": "过滤名称、IP、SNI...",
    "Search artifacts...": "搜索产物...",
    "Reset Filters": "重置筛选条件",
    "Reset All Filters": "重置所有筛选条件",
    "Reset Artifact Filters": "重置产物筛选条件",
    "No artifacts match the current filter set": "没有产物匹配当前筛选条件",
    "No proxy endpoints match current dimensional filters": "没有代理端点匹配当前筛选条件",

    // Common Actions
    "Protocol": "协议",
    "Country": "国家/地区",
    "Region": "地区",
    "Transport": "传输",
    "Security": "安全",
    "Latency": "延迟",
    "Copy": "复制",
    "Copy URI": "复制链接",
    "Copy Node URI": "复制节点 URI",
    "Copy Output": "复制输出",
    "Download": "下载",
    "Download File": "下载文件",
    "Close": "关闭",
    "Cancel": "取消",
    "Export": "导出",
    "Reset": "重置",
    "Start Scan": "开始扫描",
    "Published data updated": "已更新发布数据",
    "Language": "语言",
    "Toggle Theme": "切换主题",
    "Global Search": "全局搜索",
    "Status": "状态",
    "Actions": "操作",
    "Action": "操作",
    "Operator / Carrier": "运营商",
    "Carrier": "运营商",
    "Server Address": "服务器地址",
    "Transport Layer": "传输层",
    "Security / TLS": "安全 / TLS",
    "Health Grade": "健康等级",
    "Health": "健康状态",
    "Inspect Parameters": "检查参数",
    "Search nodes, protocols, SNI, country...": "搜索节点、协议、SNI、国家/地区...",

    // Modal & Quick Action Buttons
    "Open Clean IP Scanner": "打开可用 IP 扫描器",
    "Open Subscription Builder": "打开订阅生成器",
    "Open Protocol Decoder": "打开协议解码器",
    "GitHub Repository": "GitHub 仓库",
    "Sing-box Profile": "Sing-box 配置",
    "Xray Config": "Xray 配置",
    "Cumulative JSON": "累计 JSON",
    "Sing-box JSON": "Sing-box JSON",
    "Copy Plain URIs": "复制普通链接",
    "Copy Base64 Feed": "复制 Base64 订阅",
    "Copy Unique URIs": "复制唯一链接",
    "Load Active Nodes": "加载活跃节点",
    "Copy JSON": "复制 JSON",
    "Copy Sing-box": "复制 Sing-box",
    "Copy Clash": "复制 Clash",
    "Download SVG": "下载 SVG",
    "Copy SVG": "复制 SVG",
    "Save SVG": "保存 SVG",
    "Copy Best IP": "复制最优 IP",
    "Copy All Clean": "复制全部可用 IP",
    "Export CSV": "导出 CSV",
    "Export JSON": "导出 JSON",
    "Endpoint (Host:Port)": "端点 (主机:端口)",
    "Transport & TLS": "传输与 TLS",
    "Remark / Name": "备注 / 名称",
    "Port": "端口",
    "Credential / UUID": "凭据 / UUID",
    "SNI / ServerName": "SNI / 服务器名称",
    "Transport Network": "传输网络",
    "Reality Public Key (pbk)": "Reality 公钥 (pbk)",
    "Short ID (sid)": "短 ID (sid)",
    "gRPC ServiceName": "gRPC 服务名",
    "Sing-box Outbound Object:": "Sing-box 出站对象：",
    "Sanitize Remarks": "清理节点备注",
    "Enrich Operators": "识别运营商",
    "Ingested": "已导入",
    "Routing Profile Reference": "路由规则参考",
    "Keyboard Navigation": "快捷键导航",
    "Color Preset:": "颜色预设：",
    "Error Correction (ECC):": "纠错级别 (ECC)：",
    "Content / Proxy URI to Encode:": "待编码内容 / 代理 URI：",
    "Target IP": "目标 IP",
    "Latency (RTT)": "延迟 (RTT)",
    "Sample Count:": "采样数量：",

    // Protocol Studio & Deduplication
    "Universal Protocol Converter & Inspection Studio": "通用协议转换与分析工作室",
    "Protocol Converter & Inspection Studio": "协议转换与分析工作室",
    "Proxy Protocol Inspector": "代理协议分析器",
    "Protocol Inspector": "协议分析器",
    "Universal Converter": "通用转换器",
    "Bulk Deduplicator": "批量去重器",
    "QR Code Studio": "二维码工作室",
    "Source Proxy URIs / Base64 Subscription:": "源代理 URI / Base64 订阅：",
    "Target Client / Engine Format": "目标客户端 / 引擎格式",
    "Convert All Nodes": "转换所有节点",
    "Converted Output Result:": "转换结果：",
    "Run SHA-256 Deduplication": "执行 SHA-256 去重",
    "Duplicates Purged": "已清除重复项",
    "Unique Nodes": "唯一节点",
    "Subscription Feeds & Client Configurations": "订阅源与客户端配置",
    "Pipeline Output & Artifacts Repository": "流水线产物与订阅仓库",

    // Cloudflare Clean IP Scanner
    "Cloudflare Clean IP Scanner": "Cloudflare 可用 IP 扫描器",
    "Target CIDR Subnet:": "目标 CIDR 子网：",
    "Start Speedtest": "开始测速",
    "Rescan Subnet": "重新扫描子网",
    "No scan performed yet.": "尚未执行扫描。",
    "Ready to scan. Select range and start speedtest.": "就绪。选择网段后开始测速。",

    // Tooltips & Accessibility Labels
    "Toggle Light / Dark Theme (Press T)": "切换明暗主题 (按 T 键)",
    "Open Clean IP Scanner (Press S)": "打开可用 IP 扫描器 (按 S 键)",
    "Open Protocol Decoder (Press D)": "打开协议解码器 (按 D 键)",
    "Open Interactive System Architecture": "打开交互式系统架构图",
    "Grid Cards View (Press V)": "卡片视图 (按 V 键)",
    "Dense Data Table View (Press V)": "紧凑表格视图 (按 V 键)",
    "Raw Text / Feed View": "原始文本 / 订阅流视图",
    "Filter by Operator": "按运营商筛选",
    "Filter by Transport": "按传输协议筛选",
    "Filter by Region": "按地区筛选",
    "Filter by Health Grade": "按健康等级筛选",
    "Filter by Security": "按安全类型筛选",
    "Sort Order": "排序方式",
    "Copy Production Base64 Subscription URL": "复制生产环境 Base64 订阅链接",
    "Toggle Interactive 3D Mode": "切换交互式三维模式",
    "Toggle Inline QR Code": "切换内嵌二维码",
    "Inspect Protocol Parameters": "检查协议参数",
    "Export Sing-box Outbound Snippet": "导出 Sing-box 出站配置",
    "Scan using v2rayNG, Sing-box, NekoBox, Hiddify, or Streisand": "使用 v2rayNG、Sing-box、NekoBox、Hiddify 或 Streisand 扫描",
    "Scan with v2rayNG / Sing-box": "使用 v2rayNG / Sing-box 扫描",

    // 26 Localized Country Names
    "Germany": "德国",
    "Netherlands": "荷兰",
    "United States": "美国",
    "United Kingdom": "英国",
    "France": "法国",
    "Finland": "芬兰",
    "Singapore": "新加坡",
    "Japan": "日本",
    "South Korea": "韩国",
    "Hong Kong": "中国香港",
    "Turkey": "土耳其",
    "Sweden": "瑞典",
    "Switzerland": "瑞士",
    "Canada": "加拿大",
    "Iran": "伊朗",
    "Russia": "俄罗斯",
    "Australia": "澳大利亚",
    "Brazil": "巴西",
    "South Africa": "南非",
    "Italy": "意大利",
    "Spain": "西班牙",
    "UAE": "阿联酋",
    "India": "印度",
    "Taiwan": "中国台湾",
    "Ukraine": "乌克兰",
    "Ireland": "爱尔兰"
  },
  ru: {
    // Navigation & Primary Headers
    "GATHERX TELEMETRY": "ТЕЛЕМЕТРИЯ GATHERX",
    "NODE TELEMETRY": "ТЕЛЕМЕТРИЯ УЗЛОВ",
    "PIPELINE ONLINE": "КОНВЕЙЕР В СЕТИ",
    "IP Scanner": "Сканер IP",
    "Sub Builder": "Сборщик подписки",
    "Decoder": "Декодер",
    "3D Topology": "3D-топология",
    "Radar": "Радар",
    "Telemetry Radar": "Радар телеметрии",
    "Proxies": "Прокси",
    "Live Proxies": "Активные прокси",
    "Studio": "Студия",
    "Protocol Studio": "Студия протоколов",
    "Artifacts": "Артефакты",
    "Artifacts & Feeds": "Артефакты и подписки",
    "Architecture": "Архитектура",

    // Hero & Overview
    "Zero-Budget Sovereign Proxy Ingestion": "Автономный сбор прокси без затрат",
    "Automated Multi-Source Collector": "Автоматический сборщик прокси из нескольких источников",
    "Proxy Telemetry &": "Телеметрия прокси и",
    "Cyber Intelligence": "Киберразведка",
    "Node Diagnostics": "Диагностика узлов и сети",
    "Active Nodes": "Активные узлы",
    "Ingest Sources": "Источники сбора",
    "Published Files": "Опубликованные файлы",
    "Avg Latency": "Средняя задержка",
    "Channels": "Каналы",
    "Unmeasured": "Не измерено",
    "Copy Production Feed": "Копировать рабочую подписку",
    "Browse Verified Artifacts": "Обзор проверенных артефактов",
    "Live Node Intelligence": "Актуальные данные узлов",

    // UI Badges & Status Indicators
    "SYNCING": "Синхронизация",
    "STUDIO": "Студия",
    "RAW": "Исходный",
    "SAMPLE": "Пример",
    "LIVE": "Онлайн",
    "Bundled snapshot": "Встроенный снимок",
    "Live verified snapshot": "Актуальный проверенный снимок",
    "INTEGRITY CHECK FAILED": "Сбой проверки целостности",
    "NO LIVE PROBES": "Нет активных замеров",
    "TAP HUB": "Нажмите на узел",
    "Explore 3D Globe": "Исследовать 3D-глобус",
    "Exit 3D Mode": "Выйти из 3D-режима",
    "INTERACTIVE 3D GEO-RADAR": "ИНТЕРАКТИВНЫЙ 3D-ГЕОРАДАР",
    "CLICK HUB TO FILTER": "НАЖМИТЕ НА УЗЕЛ ДЛЯ ФИЛЬТРАЦИИ",
    "Telemetry Pipeline Synchronized & Verified": "Конвейер телеметрии синхронизирован и проверен",
    "Ingestion Pipeline Synchronized & Verified": "Конвейер сбора синхронизирован и проверен",
    "Live Carrier Latency & Ingress Matrix": "Матрица задержки операторов и входящего трафика",
    "Strategic Geo-Cluster Density": "Плотность стратегических геокластеров",
    "Geographic Node Distribution": "Географическое распределение узлов",

    // Filters & Toolbar
    "Search": "Поиск",
    "All Protocols": "Все протоколы",
    "All Countries": "Все страны",
    "All Regions": "Все регионы",
    "Geo Location": "Геолокация",
    "All Transports": "Все транспорты",
    "All Operators": "Все операторы",
    "All Health Grades": "Все уровни качества",
    "All Security Types": "Все типы безопасности",
    "Telemetry Sorting": "Сортировка телеметрии",
    "Fastest Latency": "Наименьшая задержка",
    "Top Health Score": "Лучшая оценка",
    "Name (A-Z)": "По имени (A-Z)",
    "Country (A-Z)": "По стране (A-Z)",
    "Port (Low-High)": "По порту (по возрастанию)",
    "Grid View": "Сетка",
    "Table View": "Таблица",
    "Feed View": "Лента",
    "Cards": "Карточки",
    "Table": "Таблица",
    "Raw Feed": "Сырая лента",
    "Filter name, IP, SNI...": "Фильтр по имени, IP, SNI...",
    "Search artifacts...": "Поиск артефактов...",
    "Reset Filters": "Сбросить фильтры",
    "Reset All Filters": "Сбросить все фильтры",
    "Reset Artifact Filters": "Сбросить фильтры артефактов",
    "No artifacts match the current filter set": "Нет артефактов, соответствующих текущим фильтрам",
    "No proxy endpoints match current dimensional filters": "Нет прокси, соответствующих текущим фильтрам",

    // Common Actions
    "Protocol": "Протокол",
    "Country": "Страна",
    "Region": "Регион",
    "Transport": "Транспорт",
    "Security": "Безопасность",
    "Latency": "Задержка",
    "Copy": "Копировать",
    "Copy URI": "Копировать URI",
    "Copy Node URI": "Копировать URI узла",
    "Copy Output": "Копировать результат",
    "Download": "Скачать",
    "Download File": "Скачать файл",
    "Close": "Закрыть",
    "Cancel": "Отмена",
    "Export": "Экспорт",
    "Reset": "Сбросить",
    "Start Scan": "Начать сканирование",
    "Published data updated": "Опубликованные данные обновлены",
    "Language": "Язык",
    "Toggle Theme": "Сменить тему",
    "Global Search": "Глобальный поиск",
    "Status": "Статус",
    "Actions": "Действия",
    "Action": "Действие",
    "Operator / Carrier": "Оператор связи",
    "Carrier": "Оператор",
    "Server Address": "Адрес сервера",
    "Transport Layer": "Транспортный уровень",
    "Security / TLS": "Безопасность / TLS",
    "Health Grade": "Оценка состояния",
    "Health": "Состояние",
    "Inspect Parameters": "Просмотреть параметры",
    "Search nodes, protocols, SNI, country...": "Поиск узлов, протоколов, SNI, стран...",

    // Modal & Quick Action Buttons
    "Open Clean IP Scanner": "Открыть сканер доступных IP",
    "Open Subscription Builder": "Открыть сборщик подписки",
    "Open Protocol Decoder": "Открыть декодер протоколов",
    "GitHub Repository": "Репозиторий GitHub",
    "Sing-box Profile": "Профиль Sing-box",
    "Xray Config": "Конфиг Xray",
    "Cumulative JSON": "Накопительный JSON",
    "Sing-box JSON": "JSON Sing-box",
    "Copy Plain URIs": "Копировать ссылки",
    "Copy Base64 Feed": "Копировать Base64-подписку",
    "Copy Unique URIs": "Копировать уникальные URI",
    "Load Active Nodes": "Загрузить активные узлы",
    "Copy JSON": "Копировать JSON",
    "Copy Sing-box": "Копировать Sing-box",
    "Copy Clash": "Копировать Clash",
    "Download SVG": "Скачать SVG",
    "Copy SVG": "Копировать SVG",
    "Save SVG": "Сохранить SVG",
    "Copy Best IP": "Копировать лучший IP",
    "Copy All Clean": "Копировать все чистые IP",
    "Export CSV": "Экспорт CSV",
    "Export JSON": "Экспорт JSON",
    "Endpoint (Host:Port)": "Эндпоинт (хост:порт)",
    "Transport & TLS": "Транспорт и TLS",
    "Remark / Name": "Имя / примечание",
    "Port": "Порт",
    "Credential / UUID": "Учетные данные / UUID",
    "SNI / ServerName": "SNI / Имя сервера",
    "Transport Network": "Транспортная сеть",
    "Reality Public Key (pbk)": "Публичный ключ Reality (pbk)",
    "Short ID (sid)": "Короткий ID (sid)",
    "gRPC ServiceName": "Имя сервиса gRPC",
    "Sing-box Outbound Object:": "Объект outbound для Sing-box:",
    "Sanitize Remarks": "Очистить названия",
    "Enrich Operators": "Определить операторов",
    "Ingested": "Обработано",
    "Routing Profile Reference": "Шаблон правил маршрутизации",
    "Keyboard Navigation": "Горячие клавиши",
    "Color Preset:": "Цветовая схема:",
    "Error Correction (ECC):": "Коррекция ошибок (ECC):",
    "Content / Proxy URI to Encode:": "Контент / URI для кодирования:",
    "Target IP": "Целевой IP",
    "Latency (RTT)": "Задержка (RTT)",
    "Sample Count:": "Количество проб:",

    // Protocol Studio & Deduplication
    "Universal Protocol Converter & Inspection Studio": "Универсальная студия конвертации и анализа протоколов",
    "Protocol Converter & Inspection Studio": "Студия конвертации и анализа протоколов",
    "Proxy Protocol Inspector": "Анализатор прокси-протоколов",
    "Protocol Inspector": "Анализатор протоколов",
    "Universal Converter": "Универсальный конвертер",
    "Bulk Deduplicator": "Пакетное удаление дубликатов",
    "QR Code Studio": "Студия QR-кодов",
    "Source Proxy URIs / Base64 Subscription:": "URI прокси / подписка Base64:",
    "Target Client / Engine Format": "Формат целевого клиента / движка",
    "Convert All Nodes": "Конвертировать все узлы",
    "Converted Output Result:": "Результат конвертации:",
    "Run SHA-256 Deduplication": "Дедупликация по SHA-256",
    "Duplicates Purged": "Дубликаты удалены",
    "Unique Nodes": "Уникальные узлы",
    "Subscription Feeds & Client Configurations": "Каналы подписок и конфигурации клиентов",
    "Pipeline Output & Artifacts Repository": "Репозиторий релизов и артефактов",

    // Cloudflare Clean IP Scanner
    "Cloudflare Clean IP Scanner": "Сканер доступных IP Cloudflare",
    "Target CIDR Subnet:": "Целевая подсеть CIDR:",
    "Start Speedtest": "Запустить тест скорости",
    "Rescan Subnet": "Повторно сканировать подсеть",
    "No scan performed yet.": "Сканирование ещё не выполнялось.",
    "Ready to scan. Select range and start speedtest.": "Готово к сканированию. Выберите диапазон и начните тест.",

    // Tooltips & Accessibility Labels
    "Toggle Light / Dark Theme (Press T)": "Сменить тему (клавиша T)",
    "Open Clean IP Scanner (Press S)": "Сканер доступных IP (клавиша S)",
    "Open Protocol Decoder (Press D)": "Открыть декодер протоколов (клавиша D)",
    "Open Interactive System Architecture": "Открыть интерактивную архитектуру",
    "Grid Cards View (Press V)": "Вид карточками (клавиша V)",
    "Dense Data Table View (Press V)": "Компактная таблица (клавиша V)",
    "Raw Text / Feed View": "Текстовый вид / лента",
    "Filter by Operator": "Фильтр по оператору",
    "Filter by Transport": "Фильтр по транспорту",
    "Filter by Region": "Фильтр по региону",
    "Filter by Health Grade": "Фильтр по качеству",
    "Filter by Security": "Фильтр по безопасности",
    "Sort Order": "Порядок сортировки",
    "Copy Production Base64 Subscription URL": "Копировать URL рабочей Base64-подписки",
    "Toggle Interactive 3D Mode": "Переключить интерактивный 3D-режим",
    "Toggle Inline QR Code": "Показать/скрыть QR-код",
    "Inspect Protocol Parameters": "Анализ параметров протокола",
    "Export Sing-box Outbound Snippet": "Экспорт фрагмента Sing-box",
    "Scan using v2rayNG, Sing-box, NekoBox, Hiddify, or Streisand": "Сканируйте через v2rayNG, Sing-box, NekoBox, Hiddify или Streisand",
    "Scan with v2rayNG / Sing-box": "Сканируйте через v2rayNG / Sing-box",

    // 26 Localized Country Names
    "Germany": "Германия",
    "Netherlands": "Нидерланды",
    "United States": "США",
    "United Kingdom": "Великобритания",
    "France": "Франция",
    "Finland": "Финляндия",
    "Singapore": "Сингапур",
    "Japan": "Япония",
    "South Korea": "Южная Корея",
    "Hong Kong": "Гонконг",
    "Turkey": "Турция",
    "Sweden": "Швеция",
    "Switzerland": "Швейцария",
    "Canada": "Канада",
    "Iran": "Иран",
    "Russia": "Россия",
    "Australia": "Австралия",
    "Brazil": "Бразилия",
    "South Africa": "ЮАР",
    "Italy": "Италия",
    "Spain": "Испания",
    "UAE": "ОАЭ",
    "India": "Индия",
    "Taiwan": "Тайвань",
    "Ukraine": "Украина",
    "Ireland": "Ирландия"
  }
});

export class I18nRuntime {
  constructor() {
    this.locale = "en";
    this.textSources = new WeakMap();
    this.lastWrittenText = new WeakMap();
    this.attributeSources = new WeakMap();
    this.lastWrittenAttributes = new WeakMap();
    this.observer = null;
    this.isTranslating = false;
  }

  normalizeLocale(value) {
    const locale = String(value || "").trim().toLowerCase();
    if (locale === "fa" || locale.startsWith("fa-")) return "fa";
    if (locale === "ru" || locale.startsWith("ru-")) return "ru";
    if (locale === "zh" || locale.startsWith("zh-")) return "zh-CN";
    return "en";
  }

  getStoredLocale() {
    try {
      const requested = new URLSearchParams(globalThis.location?.search || "").get("lang");
      if (requested) return requested;
      return localStorage.getItem("huntx_locale") || navigator.language || "en";
    } catch {
      return navigator.language || "en";
    }
  }

  getLocale() {
    return this.locale;
  }

  translate(message, locale = this.locale) {
    const source = String(message || "");
    if (locale === "en") return source;
    const direct = TRANSLATIONS[locale]?.[source];
    if (direct) return direct;
    return this.translatePattern(source, locale);
  }

  translatePattern(source, locale) {
    const regionMatch = source.match(/^(\d+)\s+Regions$/i);
    if (regionMatch) {
      if (locale === "fa") return `${regionMatch[1]} منطقه`;
      if (locale === "zh-CN") return `${regionMatch[1]} 个地区`;
      if (locale === "ru") return `${regionMatch[1]} регионов`;
    }
    const minimumMatch = source.match(/^Min:\s*(\d+)ms$/i);
    if (minimumMatch) {
      if (locale === "fa") return `کمینه: ${minimumMatch[1]} میلی‌ثانیه`;
      if (locale === "zh-CN") return `最低：${minimumMatch[1]} 毫秒`;
      if (locale === "ru") return `Мин.: ${minimumMatch[1]} мс`;
    }
    const copyFilteredMatch = source.match(/^Copy Filtered\s*\((\d+)\)$/i);
    if (copyFilteredMatch) {
      if (locale === "fa") return `کپی موارد فیلترشده (${copyFilteredMatch[1]})`;
      if (locale === "zh-CN") return `复制已筛选 (${copyFilteredMatch[1]})`;
      if (locale === "ru") return `Копировать выбранные (${copyFilteredMatch[1]})`;
    }
    const exploreLiveMatch = source.match(/^Explore Live Proxies\s*\((\d+)\)\s*→$/i);
    if (exploreLiveMatch) {
      if (locale === "fa") return `مشاهده پروکسی‌های زنده (${exploreLiveMatch[1]}) ←`;
      if (locale === "zh-CN") return `浏览实时代理 (${exploreLiveMatch[1]}) →`;
      if (locale === "ru") return `Обзор активных прокси (${exploreLiveMatch[1]}) →`;
    }
    const rawStreamMatch = source.match(/^Raw URI Stream\s*\((\d+)\s+matching nodes\)$/i);
    if (rawStreamMatch) {
      if (locale === "fa") return `جریان نشانی‌های خام (${rawStreamMatch[1]} گره منطبق)`;
      if (locale === "zh-CN") return `原始 URI 流 (共 ${rawStreamMatch[1]} 个匹配节点)`;
      if (locale === "ru") return `Поток сырых URI (${rawStreamMatch[1]} совпадений)`;
    }
    const nodesCountMatch = source.match(/^(\d+)\s+nodes$/i);
    if (nodesCountMatch) {
      if (locale === "fa") return `${nodesCountMatch[1]} گره`;
      if (locale === "zh-CN") return `${nodesCountMatch[1]} 个节点`;
      if (locale === "ru") return `${nodesCountMatch[1]} узлов`;
    }
    const regionsBadgeMatch = source.match(/^(\d+)\s+REGIONS$/i);
    if (regionsBadgeMatch) {
      if (locale === "fa") return `${regionsBadgeMatch[1]} منطقه`;
      if (locale === "zh-CN") return `${regionsBadgeMatch[1]} 个地区`;
      if (locale === "ru") return `${regionsBadgeMatch[1]} РЕГИОНОВ`;
    }
    const carrierFilterMatch = source.match(/^Carrier:\s*(.+)$/i);
    if (carrierFilterMatch) {
      const op = carrierFilterMatch[1];
      if (locale === "fa") return `اپراتور: ${op}`;
      if (locale === "zh-CN") return `运营商：${op}`;
      if (locale === "ru") return `Оператор: ${op}`;
    }
    const transportFilterMatch = source.match(/^Transport:\s*(.+)$/i);
    if (transportFilterMatch) {
      const tr = transportFilterMatch[1];
      if (locale === "fa") return `لایه انتقال: ${tr}`;
      if (locale === "zh-CN") return `传输协议：${tr}`;
      if (locale === "ru") return `Транспорт: ${tr}`;
    }
    const gradeMatch = source.match(/^Grade\s+([A-Za-z0-9+-]+)$/i);
    if (gradeMatch) {
      const gr = gradeMatch[1];
      if (locale === "fa") return `سطح ${gr}`;
      if (locale === "zh-CN") return `等级 ${gr}`;
      if (locale === "ru") return `Класс ${gr}`;
    }
    const countryOptionMatch = source.match(/^(\S+)\s+(.+?)\s+\(([A-Z]{2})\)$/);
    if (countryOptionMatch) {
      const flag = countryOptionMatch[1];
      const countryEn = countryOptionMatch[2].trim();
      const code = countryOptionMatch[3];
      const translatedCountry = TRANSLATIONS[locale]?.[countryEn] || countryEn;
      return `${flag} ${translatedCountry} (${code})`;
    }
    const geoCarrierMatch = source.match(/^(\S+)\s+(.+?)\s+•\s+(.+)$/);
    if (geoCarrierMatch) {
      const flag = geoCarrierMatch[1];
      const countryEn = geoCarrierMatch[2].trim();
      const carrier = geoCarrierMatch[3];
      const translatedCountry = TRANSLATIONS[locale]?.[countryEn] || countryEn;
      return `${flag} ${translatedCountry} • ${carrier}`;
    }
    return source;
  }

  translateTextNode(node) {
    if (!node?.parentElement || node.parentElement.closest("script, style, code, pre, [data-i18n-ignore]")) return;
    if (!this.textSources.has(node)) this.textSources.set(node, node.nodeValue || "");
    const source = this.textSources.get(node);
    const content = source.trim();
    if (!content) return;
    const translated = this.translate(content);
    const output = source.replace(content, translated);
    if (node.nodeValue !== output) {
      const pending = this.lastWrittenText.get(node);
      this.lastWrittenText.set(node, { value: output, count: (pending?.count || 0) + 1 });
      node.nodeValue = output;
    }
  }

  translateAttributes(element) {
    if (!(element instanceof Element) || element.closest("[data-i18n-ignore]")) return;
    let sources = this.attributeSources.get(element);
    if (!sources) {
      sources = new Map();
      this.attributeSources.set(element, sources);
    }
    for (const name of ["aria-label", "title", "placeholder"]) {
      if (element.hasAttribute(name) && !sources.has(name)) sources.set(name, element.getAttribute(name));
      if (sources.has(name)) {
        const output = this.translate(sources.get(name));
        if (element.getAttribute(name) !== output) {
          let writes = this.lastWrittenAttributes.get(element);
          if (!writes) {
            writes = new Map();
            this.lastWrittenAttributes.set(element, writes);
          }
          const pending = writes.get(name);
          writes.set(name, { value: output, count: (pending?.count || 0) + 1 });
          element.setAttribute(name, output);
        }
      }
    }
  }

  translateTree(root = document.documentElement) {
    if (!root) return;
    if (root.nodeType === Node.TEXT_NODE) {
      this.translateTextNode(root);
      return;
    }
    if (root.nodeType !== Node.ELEMENT_NODE && root.nodeType !== Node.DOCUMENT_NODE) return;
    if (root.nodeType === Node.ELEMENT_NODE) this.translateAttributes(root);
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
    let node = walker.nextNode();
    while (node) {
      if (node.nodeType === Node.TEXT_NODE) this.translateTextNode(node);
      else this.translateAttributes(node);
      node = walker.nextNode();
    }
  }

  setLocale(value, { persist = true } = {}) {
    const locale = this.normalizeLocale(value);
    this.locale = locale;
    document.documentElement.lang = locale;
    document.documentElement.dir = locale === "fa" ? "rtl" : "ltr";
    if (persist) {
      try { localStorage.setItem("huntx_locale", locale); } catch {}
    }
    this.isTranslating = true;
    try {
      this.translateTree();
    } finally {
      this.isTranslating = false;
    }
    const selector = document.getElementById("language-selector");
    if (selector) selector.value = locale;
    document.dispatchEvent(new CustomEvent("huntx:localechange", { detail: { locale } }));
    return locale;
  }

  start() {
    if (typeof document === "undefined" || this.observer) return;
    this.setLocale(this.getStoredLocale(), { persist: false });
    this.observer = new MutationObserver((mutations) => {
      if (this.isTranslating) return;
      for (const mutation of mutations) {
        if (mutation.type === "characterData") {
          const currentValue = mutation.target.nodeValue || "";
          const pending = this.lastWrittenText.get(mutation.target);
          if (pending?.value === currentValue && pending.count > 0) {
            if (pending.count === 1) this.lastWrittenText.delete(mutation.target);
            else pending.count -= 1;
            continue;
          }
          this.textSources.set(mutation.target, currentValue);
          this.isTranslating = true;
          try { this.translateTextNode(mutation.target); } finally { this.isTranslating = false; }
          continue;
        }
        if (mutation.type === "attributes") {
          const attributeName = mutation.attributeName;
          const currentValue = mutation.target.getAttribute(attributeName);
          const writes = this.lastWrittenAttributes.get(mutation.target);
          const pending = writes?.get(attributeName);
          if (pending?.value === currentValue && pending.count > 0) {
            if (pending.count === 1) writes.delete(attributeName);
            else pending.count -= 1;
            if (writes.size === 0) this.lastWrittenAttributes.delete(mutation.target);
            continue;
          }
          const sources = this.attributeSources.get(mutation.target);
          if (sources) sources.delete(attributeName);
          this.isTranslating = true;
          try { this.translateAttributes(mutation.target); } finally { this.isTranslating = false; }
          continue;
        }
        for (const node of mutation.addedNodes) {
          this.isTranslating = true;
          try { this.translateTree(node); } finally { this.isTranslating = false; }
        }
      }
    });
    this.observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["aria-label", "title", "placeholder"],
      characterData: true,
      childList: true,
      subtree: true
    });
  }
}

export const i18n = new I18nRuntime();
i18n.start();
