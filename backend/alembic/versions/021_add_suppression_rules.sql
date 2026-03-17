-- 创建屏蔽规则表 (Create Suppression Rules Table)
-- 用于统一管理各种监控维度的告警屏蔽规则
-- Manage unified suppression rules for various monitoring dimensions

-- 创建表
CREATE TABLE IF NOT EXISTS suppression_rules (
    id SERIAL PRIMARY KEY,
    resource_type VARCHAR(50) NOT NULL DEFAULT 'general',
    resource_id INTEGER,
    resource_pattern VARCHAR(500),
    alert_rule_id INTEGER,
    start_time TIMESTAMP WITH TIME ZONE,
    end_time TIMESTAMP WITH TIME ZONE,
    suppress_alerts BOOLEAN NOT NULL DEFAULT true,
    suppress_notifications BOOLEAN NOT NULL DEFAULT true,
    suppress_ai_analysis BOOLEAN NOT NULL DEFAULT true,
    suppress_log_scan BOOLEAN NOT NULL DEFAULT false,
    reason TEXT,
    created_by VARCHAR(255),
    is_active BOOLEAN NOT NULL DEFAULT true,
    match_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- 创建索引
CREATE INDEX IF NOT EXISTS ix_suppression_rules_resource_type ON suppression_rules(resource_type);
CREATE INDEX IF NOT EXISTS ix_suppression_rules_resource_id ON suppression_rules(resource_id);
CREATE INDEX IF NOT EXISTS ix_suppression_rules_alert_rule_id ON suppression_rules(alert_rule_id);
CREATE INDEX IF NOT EXISTS ix_suppression_rules_is_active ON suppression_rules(is_active);
CREATE INDEX IF NOT EXISTS ix_suppression_rules_start_time ON suppression_rules(start_time);
CREATE INDEX IF NOT EXISTS ix_suppression_rules_end_time ON suppression_rules(end_time);

-- 创建外键约束
ALTER TABLE suppression_rules DROP CONSTRAINT IF EXISTS fk_suppression_rules_alert_rule_id;
ALTER TABLE suppression_rules ADD CONSTRAINT fk_suppression_rules_alert_rule_id
    FOREIGN KEY (alert_rule_id) REFERENCES alert_rules(id) ON DELETE SET NULL;
