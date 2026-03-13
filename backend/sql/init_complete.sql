-- VigilOps 完整数据库初始化脚本
-- 基于生产环境实际表结构生成
-- 执行方式: docker compose exec -T postgres psql -U vigilops -d vigilops -f init_complete.sql

-- ============================================
-- 核心功能表
-- ============================================

-- ── Users (用户表) ─────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'viewer',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Agent Tokens (Agent 令牌) ─────────────────────────
CREATE TABLE IF NOT EXISTS agent_tokens (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    token_prefix VARCHAR(8) NOT NULL,
    created_by INTEGER NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMPTZ
);
ALTER TABLE agent_tokens ADD CONSTRAINT fk_agent_tokens_created_by FOREIGN KEY (created_by) REFERENCES users(id);

-- ── Settings (系统配置) ───────────────────────────────
CREATE TABLE IF NOT EXISTS settings (
    key VARCHAR(255) PRIMARY KEY,
    value TEXT NOT NULL DEFAULT '',
    description VARCHAR(500),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── Audit Logs (审计日志) ─────────────────────────────
CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    action VARCHAR(50) NOT NULL,
    resource_type VARCHAR(50) NOT NULL,
    resource_id INTEGER,
    detail TEXT,
    ip_address VARCHAR(45),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE audit_logs ADD CONSTRAINT fk_audit_logs_user_id FOREIGN KEY (user_id) REFERENCES users(id);
CREATE INDEX idx_audit_logs_action ON audit_logs(action);
CREATE INDEX idx_audit_logs_created_at ON audit_logs(created_at);
CREATE INDEX idx_audit_logs_resource_type ON audit_logs(resource_type);

-- ============================================
-- 监控数据表
-- ============================================

-- ── Hosts (主机表) ───────────────────────────────────
CREATE TABLE IF NOT EXISTS hosts (
    id SERIAL PRIMARY KEY,
    hostname VARCHAR(255) NOT NULL,
    ip_address VARCHAR(45),
    os VARCHAR(100),
    os_version VARCHAR(100),
    arch VARCHAR(50),
    cpu_cores INTEGER,
    memory_total_mb INTEGER,
    agent_version VARCHAR(50),
    status VARCHAR(20) NOT NULL DEFAULT 'online',
    tags JSON,
    group_name VARCHAR(100),
    agent_token_id INTEGER NOT NULL,
    last_heartbeat TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    display_name VARCHAR(255),
    private_ip VARCHAR(45),
    public_ip VARCHAR(45),
    network_info JSON
);
ALTER TABLE hosts ADD CONSTRAINT fk_hosts_agent_token_id FOREIGN KEY (agent_token_id) REFERENCES agent_tokens(id);
CREATE UNIQUE INDEX idx_hosts_hostname ON hosts(hostname);
CREATE INDEX idx_hosts_status ON hosts(status);

-- ── Host Metrics (主机指标) ───────────────────────────
CREATE TABLE IF NOT EXISTS host_metrics (
    id SERIAL PRIMARY KEY,
    host_id INTEGER NOT NULL,
    cpu_percent DOUBLE PRECISION,
    cpu_load_1 DOUBLE PRECISION,
    cpu_load_5 DOUBLE PRECISION,
    cpu_load_15 DOUBLE PRECISION,
    memory_used_mb INTEGER,
    memory_percent DOUBLE PRECISION,
    disk_used_mb INTEGER,
    disk_total_mb INTEGER,
    disk_percent DOUBLE PRECISION,
    net_bytes_sent BIGINT,
    net_bytes_recv BIGINT,
    net_send_rate_kb DOUBLE PRECISION,
    net_recv_rate_kb DOUBLE PRECISION,
    net_packet_loss_rate DOUBLE PRECISION,
    server_id INTEGER,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE host_metrics ADD CONSTRAINT fk_host_metrics_host_id FOREIGN KEY (host_id) REFERENCES hosts(id);
CREATE INDEX idx_host_metrics_host_id ON host_metrics(host_id);
CREATE INDEX idx_host_metrics_recorded_at ON host_metrics(recorded_at);

-- ── Services (服务表) ─────────────────────────────────
CREATE TABLE IF NOT EXISTS services (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    type VARCHAR(20) NOT NULL,
    target VARCHAR(500) NOT NULL,
    check_interval INTEGER NOT NULL DEFAULT 60,
    timeout INTEGER NOT NULL DEFAULT 10,
    expected_status INTEGER,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    status VARCHAR(20) NOT NULL DEFAULT 'unknown',
    host_id INTEGER,
    category VARCHAR(30),
    tags JSON,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE services ADD CONSTRAINT fk_services_host_id FOREIGN KEY (host_id) REFERENCES hosts(id);

-- ── Service Checks (服务检查记录) ─────────────────────
CREATE TABLE IF NOT EXISTS service_checks (
    id SERIAL PRIMARY KEY,
    service_id INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL,
    response_time_ms DOUBLE PRECISION,
    status_code INTEGER,
    error VARCHAR(500),
    checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE service_checks ADD CONSTRAINT fk_service_checks_service_id FOREIGN KEY (service_id) REFERENCES services(id);
CREATE INDEX idx_service_checks_service_id ON service_checks(service_id);
CREATE INDEX idx_service_checks_checked_at ON service_checks(checked_at);

-- ── Log Entries (日志采集) ────────────────────────────
CREATE TABLE IF NOT EXISTS log_entries (
    id BIGSERIAL PRIMARY KEY,
    host_id INTEGER NOT NULL,
    service VARCHAR(255),
    source VARCHAR(512),
    level VARCHAR(20),
    message TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE log_entries ADD CONSTRAINT fk_log_entries_host_id FOREIGN KEY (host_id) REFERENCES hosts(id);
CREATE INDEX idx_log_entries_host_id ON log_entries(host_id);
CREATE INDEX idx_log_entries_timestamp ON log_entries(timestamp);
CREATE INDEX idx_log_entries_level ON log_entries(level);

-- ── Monitored Databases (数据库监控) ───────────────────
CREATE TABLE IF NOT EXISTS monitored_databases (
    id SERIAL PRIMARY KEY,
    host_id INTEGER NOT NULL,
    name VARCHAR(255) NOT NULL,
    db_type VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'unknown',
    slow_queries_detail JSON,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE monitored_databases ADD CONSTRAINT fk_monitored_databases_host_id FOREIGN KEY (host_id) REFERENCES hosts(id);

-- ── DB Metrics (数据库指标) ───────────────────────────
CREATE TABLE IF NOT EXISTS db_metrics (
    id BIGSERIAL PRIMARY KEY,
    database_id INTEGER NOT NULL,
    connections_total INTEGER,
    connections_active INTEGER,
    database_size_mb DOUBLE PRECISION,
    slow_queries INTEGER,
    tables_count INTEGER,
    transactions_committed BIGINT,
    transactions_rolled_back BIGINT,
    qps DOUBLE PRECISION,
    tablespace_used_pct DOUBLE PRECISION,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE db_metrics ADD CONSTRAINT fk_db_metrics_database_id FOREIGN KEY (database_id) REFERENCES monitored_databases(id);
CREATE INDEX idx_db_metrics_database_id ON db_metrics(database_id);
CREATE INDEX idx_db_metrics_recorded_at ON db_metrics(recorded_at);

-- ============================================
-- 告警系统表
-- ============================================

-- ── Alert Rules (告警规则) ────────────────────────────
CREATE TABLE IF NOT EXISTS alert_rules (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    name_en VARCHAR(255),
    description TEXT,
    severity VARCHAR(20) NOT NULL,
    metric VARCHAR(100) NOT NULL,
    operator VARCHAR(10) NOT NULL DEFAULT '>',
    threshold DOUBLE PRECISION NOT NULL,
    duration_seconds INTEGER NOT NULL,
    is_builtin BOOLEAN NOT NULL DEFAULT FALSE,
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    target_type VARCHAR(20) NOT NULL DEFAULT 'host',
    target_filter JSON,
    rule_type VARCHAR(20),
    log_keyword VARCHAR(500),
    log_level VARCHAR(20),
    log_service VARCHAR(255),
    db_metric_name VARCHAR(50),
    db_id INTEGER,
    cooldown_seconds INTEGER NOT NULL DEFAULT 300,
    silence_start TIME WITHOUT TIME ZONE,
    silence_end TIME WITHOUT TIME ZONE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notification_channel_ids JSON,
    continuous_alert BOOLEAN NOT NULL DEFAULT TRUE
);

-- ── Alerts (告警记录) ─────────────────────────────────
CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    rule_id INTEGER NOT NULL,
    host_id INTEGER,
    service_id INTEGER,
    severity VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'firing',
    title VARCHAR(500) NOT NULL,
    title_en VARCHAR(500),
    message TEXT,
    metric_value DOUBLE PRECISION,
    threshold DOUBLE PRECISION,
    fired_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by INTEGER,
    escalation_level INTEGER NOT NULL DEFAULT 0,
    last_escalated_at TIMESTAMPTZ,
    next_escalation_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE alerts ADD CONSTRAINT fk_alerts_rule_id FOREIGN KEY (rule_id) REFERENCES alert_rules(id);
ALTER TABLE alerts ADD CONSTRAINT fk_alerts_host_id FOREIGN KEY (host_id) REFERENCES hosts(id);
ALTER TABLE alerts ADD CONSTRAINT fk_alerts_service_id FOREIGN KEY (service_id) REFERENCES services(id);
ALTER TABLE alerts ADD CONSTRAINT fk_alerts_acknowledged_by FOREIGN KEY (acknowledged_by) REFERENCES users(id);
CREATE INDEX idx_alerts_rule_id ON alerts(rule_id);
CREATE INDEX idx_alerts_host_id ON alerts(host_id);
CREATE INDEX idx_alerts_service_id ON alerts(service_id);
CREATE INDEX idx_alerts_status ON alerts(status);
CREATE INDEX idx_alerts_fired_at ON alerts(fired_at);

-- ── Alert Groups (告警聚合) ────────────────────────────
CREATE TABLE IF NOT EXISTS alert_groups (
    id SERIAL PRIMARY KEY,
    group_key VARCHAR(500) NOT NULL,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    severity VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    alert_count INTEGER NOT NULL,
    rule_ids JSON,
    host_ids JSON,
    service_ids JSON,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    last_occurrence TIMESTAMPTZ NOT NULL,
    notification_sent BOOLEAN NOT NULL DEFAULT FALSE,
    notification_sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_alert_groups_group_key ON alert_groups(group_key);
CREATE INDEX idx_alert_groups_status ON alert_groups(status);
CREATE INDEX idx_alert_groups_last_occurrence ON alert_groups(last_occurrence);

-- ── Alert Deduplications (告警去重) ────────────────────
CREATE TABLE IF NOT EXISTS alert_deduplications (
    id SERIAL PRIMARY KEY,
    fingerprint VARCHAR(255) NOT NULL UNIQUE,
    rule_id INTEGER NOT NULL,
    host_id INTEGER,
    service_id INTEGER,
    first_violation_time TIMESTAMPTZ NOT NULL,
    occurrence_count INTEGER NOT NULL,
    suppressed BOOLEAN NOT NULL DEFAULT FALSE,
    suppression_reason VARCHAR(255),
    alert_group_id INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    first_alert_time TIMESTAMPTZ,
    last_alert_time TIMESTAMPTZ,
    last_check_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    alert_sent_count INTEGER NOT NULL DEFAULT 0,
    alert_triggered BOOLEAN NOT NULL DEFAULT FALSE,
    recovery_start_time TIMESTAMPTZ
);
ALTER TABLE alert_deduplications ADD CONSTRAINT fk_alert_deduplications_alert_group_id FOREIGN KEY (alert_group_id) REFERENCES alert_groups(id);
CREATE INDEX idx_alert_deduplications_fingerprint ON alert_deduplications(fingerprint);
CREATE INDEX idx_alert_deduplications_rule_id ON alert_deduplications(rule_id);

-- ── Escalation Rules (升级规则) ───────────────────────
CREATE TABLE IF NOT EXISTS escalation_rules (
    id SERIAL PRIMARY KEY,
    alert_rule_id INTEGER NOT NULL,
    name VARCHAR(255) NOT NULL,
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    escalation_levels JSON NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE escalation_rules ADD CONSTRAINT fk_escalation_rules_alert_rule_id FOREIGN KEY (alert_rule_id) REFERENCES alert_rules(id);

-- ── Alert Escalations (告警升级记录) ───────────────────
CREATE TABLE IF NOT EXISTS alert_escalations (
    id SERIAL PRIMARY KEY,
    alert_id INTEGER NOT NULL,
    escalation_rule_id INTEGER,
    from_severity VARCHAR(20) NOT NULL,
    to_severity VARCHAR(20) NOT NULL,
    escalation_level INTEGER NOT NULL,
    escalated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    escalated_by_system BOOLEAN NOT NULL,
    message TEXT
);
ALTER TABLE alert_escalations ADD CONSTRAINT fk_alert_escalations_alert_id FOREIGN KEY (alert_id) REFERENCES alerts(id);
ALTER TABLE alert_escalations ADD CONSTRAINT fk_alert_escalations_escalation_rule_id FOREIGN KEY (escalation_rule_id) REFERENCES escalation_rules(id);
CREATE INDEX idx_alert_escalations_alert_id ON alert_escalations(alert_id);

-- ── On Call Groups (值班组) ────────────────────────────
CREATE TABLE IF NOT EXISTS on_call_groups (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── On Call Schedules (值班排期) ───────────────────────
CREATE TABLE IF NOT EXISTS on_call_schedules (
    id SERIAL PRIMARY KEY,
    group_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE on_call_schedules ADD CONSTRAINT fk_on_call_schedules_group_id FOREIGN KEY (group_id) REFERENCES on_call_groups(id);
ALTER TABLE on_call_schedules ADD CONSTRAINT fk_on_call_schedules_user_id FOREIGN KEY (user_id) REFERENCES users(id);

-- ============================================
-- 通知系统表
-- ============================================

-- ── Notification Channels (通知渠道) ───────────────────
CREATE TABLE IF NOT EXISTS notification_channels (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    type VARCHAR(50) NOT NULL DEFAULT 'webhook',
    config JSON NOT NULL,
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Notification Logs (通知日志) ───────────────────────
CREATE TABLE IF NOT EXISTS notification_logs (
    id SERIAL PRIMARY KEY,
    alert_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL,
    response_code INTEGER,
    error TEXT,
    retries INTEGER NOT NULL DEFAULT 0,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE notification_logs ADD CONSTRAINT fk_notification_logs_alert_id FOREIGN KEY (alert_id) REFERENCES alerts(id);
ALTER TABLE notification_logs ADD CONSTRAINT fk_notification_logs_channel_id FOREIGN KEY (channel_id) REFERENCES notification_channels(id);
CREATE INDEX idx_notification_logs_alert_id ON notification_logs(alert_id);

-- ── Notification Templates (通知模板) ──────────────────
CREATE TABLE IF NOT EXISTS notification_templates (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    channel_type VARCHAR(50) NOT NULL,
    subject_template VARCHAR(500),
    body_template TEXT NOT NULL,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================
-- 服务拓扑表
-- ============================================

-- ── Service Dependencies (服务依赖) ───────────────────
CREATE TABLE IF NOT EXISTS service_dependencies (
    id SERIAL PRIMARY KEY,
    source_service_id INTEGER NOT NULL,
    target_service_id INTEGER NOT NULL,
    dependency_type VARCHAR(50) NOT NULL,
    description VARCHAR(200),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE service_dependencies ADD CONSTRAINT fk_service_dependencies_source FOREIGN KEY (source_service_id) REFERENCES services(id);
ALTER TABLE service_dependencies ADD CONSTRAINT fk_service_dependencies_target FOREIGN KEY (target_service_id) REFERENCES services(id);

-- ── Topology Layouts (拓扑布局) ─────────────────────────
CREATE TABLE IF NOT EXISTS topology_layouts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    name VARCHAR(100) NOT NULL,
    positions JSON NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE topology_layouts ADD CONSTRAINT fk_topology_layouts_user_id FOREIGN KEY (user_id) REFERENCES users(id);

-- ── Servers (多服务器拓扑) ─────────────────────────────
CREATE TABLE IF NOT EXISTS servers (
    id SERIAL PRIMARY KEY,
    hostname VARCHAR(255) NOT NULL,
    ip_address VARCHAR(45),
    label VARCHAR(255),
    tags JSON,
    status VARCHAR(20) NOT NULL DEFAULT 'online',
    last_seen TIMESTAMPTZ,
    is_simulated BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Service Groups (服务分组) ──────────────────────────
CREATE TABLE IF NOT EXISTS service_groups (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    category VARCHAR(50),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Server Services (服务器服务关联) ───────────────────
CREATE TABLE IF NOT EXISTS server_services (
    id SERIAL PRIMARY KEY,
    server_id INTEGER NOT NULL,
    group_id INTEGER NOT NULL,
    port INTEGER,
    pid INTEGER,
    status VARCHAR(20) NOT NULL,
    cpu_percent DOUBLE PRECISION NOT NULL,
    mem_mb DOUBLE PRECISION NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE server_services ADD CONSTRAINT fk_server_services_server_id FOREIGN KEY (server_id) REFERENCES servers(id);
ALTER TABLE server_services ADD CONSTRAINT fk_server_services_group_id FOREIGN KEY (group_id) REFERENCES service_groups(id);

-- ── Nginx Upstreams (Nginx 上游) ───────────────────────
CREATE TABLE IF NOT EXISTS nginx_upstreams (
    id SERIAL PRIMARY KEY,
    server_id INTEGER NOT NULL,
    upstream_name VARCHAR(255) NOT NULL,
    backend_address VARCHAR(255) NOT NULL,
    weight INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL,
    parsed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE nginx_upstreams ADD CONSTRAINT fk_nginx_upstreams_server_id FOREIGN KEY (server_id) REFERENCES servers(id);

-- ============================================
-- SLA 管理表
-- ============================================

-- ── SLA Rules ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sla_rules (
    id SERIAL PRIMARY KEY,
    service_id INTEGER NOT NULL,
    name VARCHAR(200) NOT NULL,
    target_percent NUMERIC NOT NULL,
    calculation_window VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE sla_rules ADD CONSTRAINT fk_sla_rules_service_id FOREIGN KEY (service_id) REFERENCES services(id);

-- ── SLA Violations ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS sla_violations (
    id SERIAL PRIMARY KEY,
    sla_rule_id INTEGER NOT NULL,
    service_id INTEGER NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    duration_seconds INTEGER,
    description VARCHAR(500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE sla_violations ADD CONSTRAINT fk_sla_violations_sla_rule_id FOREIGN KEY (sla_rule_id) REFERENCES sla_rules(id);
ALTER TABLE sla_violations ADD CONSTRAINT fk_sla_violations_service_id FOREIGN KEY (service_id) REFERENCES services(id);
CREATE INDEX idx_sla_violations_service_id ON sla_violations(service_id);
CREATE INDEX idx_sla_violations_started_at ON sla_violations(started_at);

-- ============================================
-- AI 功能表
-- ============================================

-- ── AI Insights (AI 分析结果) ─────────────────────────
CREATE TABLE IF NOT EXISTS ai_insights (
    id SERIAL PRIMARY KEY,
    insight_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    title VARCHAR(500) NOT NULL,
    summary TEXT NOT NULL,
    details JSON,
    related_host_id INTEGER,
    related_alert_id INTEGER,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE ai_insights ADD CONSTRAINT fk_ai_insights_related_host_id FOREIGN KEY (related_host_id) REFERENCES hosts(id);
ALTER TABLE ai_insights ADD CONSTRAINT fk_ai_insights_related_alert_id FOREIGN KEY (related_alert_id) REFERENCES alerts(id);
CREATE INDEX idx_ai_insights_type ON ai_insights(insight_type);
CREATE INDEX idx_ai_insights_created_at ON ai_insights(created_at);

-- ── Remediation Logs (自动修复日志) ────────────────────
CREATE TABLE IF NOT EXISTS remediation_logs (
    id SERIAL PRIMARY KEY,
    alert_id INTEGER NOT NULL,
    host_id INTEGER,
    status VARCHAR(20) NOT NULL,
    risk_level VARCHAR(10),
    runbook_name VARCHAR(100),
    diagnosis_json JSON,
    command_results_json JSON,
    verification_passed BOOLEAN,
    blocked_reason TEXT,
    triggered_by VARCHAR(20) NOT NULL,
    approved_by INTEGER,
    approved_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE remediation_logs ADD CONSTRAINT fk_remediation_logs_alert_id FOREIGN KEY (alert_id) REFERENCES alerts(id);
ALTER TABLE remediation_logs ADD CONSTRAINT fk_remediation_logs_host_id FOREIGN KEY (host_id) REFERENCES hosts(id);
ALTER TABLE remediation_logs ADD CONSTRAINT fk_remediation_logs_approved_by FOREIGN KEY (approved_by) REFERENCES users(id);
CREATE INDEX idx_remediation_logs_alert_id ON remediation_logs(alert_id);
CREATE INDEX idx_remediation_logs_status ON remediation_logs(status);

-- ── AI Feedback (AI 反馈) ─────────────────────────────
CREATE TABLE IF NOT EXISTS ai_feedback (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    session_id VARCHAR(100),
    message_id VARCHAR(100),
    ai_response TEXT NOT NULL,
    user_question TEXT,
    rating INTEGER NOT NULL,
    feedback_type VARCHAR(50) NOT NULL,
    feedback_text TEXT,
    is_helpful BOOLEAN,
    context JSON,
    ai_confidence DOUBLE PRECISION,
    response_time_ms INTEGER,
    is_reviewed BOOLEAN DEFAULT FALSE,
    reviewer_notes TEXT,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
);
ALTER TABLE ai_feedback ADD CONSTRAINT fk_ai_feedback_user_id FOREIGN KEY (user_id) REFERENCES users(id);

-- ── AI Feedback Summary (AI 反馈汇总) ─────────────────
CREATE TABLE IF NOT EXISTS ai_feedback_summary (
    id SERIAL PRIMARY KEY,
    period_type VARCHAR(20) NOT NULL,
    period_start TIMESTAMP NOT NULL,
    period_end TIMESTAMP NOT NULL,
    total_feedback INTEGER,
    avg_rating DOUBLE PRECISION,
    helpful_count INTEGER,
    not_helpful_count INTEGER,
    feedback_by_type JSON,
    rating_distribution JSON,
    avg_response_time_ms DOUBLE PRECISION,
    avg_confidence DOUBLE PRECISION,
    created_at TIMESTAMP
);

-- ============================================
-- 报告和仪表盘表
-- ============================================

-- ── Reports (运维报告) ────────────────────────────────
CREATE TABLE IF NOT EXISTS reports (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    report_type VARCHAR(20) NOT NULL,
    period_start TIMESTAMP NOT NULL,
    period_end TIMESTAMP NOT NULL,
    content TEXT NOT NULL,
    summary TEXT NOT NULL,
    status VARCHAR(20) NOT NULL,
    generated_by INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
ALTER TABLE reports ADD CONSTRAINT fk_reports_generated_by FOREIGN KEY (generated_by) REFERENCES users(id);

-- ── Dashboard Components (仪表盘组件) ─────────────────
CREATE TABLE IF NOT EXISTS dashboard_components (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description VARCHAR(255),
    category VARCHAR(50),
    default_config JSON,
    is_enabled BOOLEAN,
    sort_order INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── Dashboard Layouts (仪表盘布局) ────────────────────
CREATE TABLE IF NOT EXISTS dashboard_layouts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    name VARCHAR(100) NOT NULL,
    description VARCHAR(255),
    is_active BOOLEAN,
    is_preset BOOLEAN,
    grid_cols INTEGER,
    config JSON NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE dashboard_layouts ADD CONSTRAINT fk_dashboard_layouts_user_id FOREIGN KEY (user_id) REFERENCES users(id);

-- ============================================
-- 默认数据
-- ============================================

-- 默认仪表盘组件
INSERT INTO dashboard_components (id, name, description, category, default_config, is_enabled, sort_order) VALUES
('hosts-overview', '主机概览', '显示主机总数、在线/离线状态分布', 'overview', '{"title": "主机概览", "showStatus": true}', true, 1),
('alerts-summary', '告警汇总', '显示当前活跃告警数量和严重级别分布', 'overview', '{"title": "告警汇总", "showSeverity": true}', true, 2),
('metrics-chart', '指标趋势图', '展示 CPU/内存/磁盘使用率趋势', 'charts', '{"title": "指标趋势", "metrics": ["cpu", "memory", "disk"], "timeRange": "1h"}', true, 3),
('service-status', '服务状态', '展示所有服务的运行状态', 'services', '{"title": "服务状态", "groupBy": "type"}', true, 4),
('topology-view', '服务拓扑', '可视化展示服务依赖关系', 'topology', '{"title": "服务拓扑", "autoLayout": true}', true, 5),
('recent-alerts', '最近告警', '显示最近触发的告警列表', 'alerts', '{"title": "最近告警", "limit": 10}', true, 6),
('log-keywords', '日志关键词', '日志中出现频率最高的关键词', 'logs', '{"title": "日志关键词", "limit": 20}', true, 7),
('sla-overview', 'SLA 概览', '服务可用性 SLA 指标', 'sla', '{"title": "SLA 概览", "target": 99.9}', true, 8)
ON CONFLICT (id) DO NOTHING;

-- 完成
SELECT 'VigilOps 数据库初始化完成！' AS status;
SELECT COUNT(*) AS table_count FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE';
