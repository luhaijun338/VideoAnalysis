# EDR-PAM 关联分析

独立于录像分析（VideoAnalysis）的 PAM 安全风险审计分析服务，复用同一 PostgreSQL 实例，使用独立数据库 `edr_pam`。

## 架构隔离

| 项目 | 后端端口 | 前端端口 | 数据库 |
|------|----------|----------|--------|
| VideoAnalysis | 8000 | 5173 | `video_analysis` |
| EDR-PAM | 8001 | 5174 | `edr_pam` |

## 功能模块

- **风险总览**：统计卡片、7 日趋势、等级分布、模型命中、Top 账号、最新告警
- **告警研判**：筛选查询、详情抽屉（时间线 / 证据 / 处置记录）、联动处置
- **处置联动**：4 类联动规则开关、权重配置、处置记录
- **模型配置**：4 个分析模型详情与开关
- **审计证据链**：合规报告生成、多源证据链、样例审计报告

样例数据来自 HTML 原型，首次启动 API 时自动写入数据库。

## 启动

### 1. 创建数据库（若尚未存在）

```bash
docker exec -i video-analysis-db psql -U va -d postgres -c "CREATE DATABASE edr_pam;" 2>/dev/null || true
```

### 2. 后端

```bash
cd edr-pam/backend
pip install -e ".[dev]"
uvicorn edr_pam.api:app --host 127.0.0.1 --port 8001 --reload
```

### 3. 前端

```bash
cd edr-pam/frontend
npm install
npm run dev
```

浏览器访问 http://localhost:5174

## 环境变量

可在项目根目录 `.env` 或 `edr-pam/backend/.env` 中设置：

```
DATABASE_URL=postgresql+psycopg://va:va@localhost:5432/edr_pam
```

## 测试

```bash
cd edr-pam/backend
pytest
```
