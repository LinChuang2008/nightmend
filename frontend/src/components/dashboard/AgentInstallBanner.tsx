/**
 * Agent 安装引导 Banner
 *
 * 当仪表盘 hosts=0 时显示，引导用户安装 Agent。
 * - 显示一键安装命令（含 API Token）
 * - 支持一键复制
 * - 可关闭（localStorage 记录关闭状态）
 */
import { useState, useEffect } from 'react';
import { Alert, Button, Space, Typography, Spin, message } from 'antd';
import { CopyOutlined, CheckOutlined, CloseOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import api from '../../services/api';

const DISMISSED_KEY = 'vigilops-agent-banner-dismissed';

interface AgentTokenInfo {
  id: string;
  name: string;
  token_prefix: string;
  is_active: boolean;
}

export default function AgentInstallBanner() {
  const { t } = useTranslation();
  const [dismissed, setDismissed] = useState(() => localStorage.getItem(DISMISSED_KEY) === '1');
  const [token, setToken] = useState<string>('');
  const [loadingToken, setLoadingToken] = useState(true);
  const [copied, setCopied] = useState(false);
  const [messageApi, contextHolder] = message.useMessage();

  useEffect(() => {
    if (dismissed) return;
    fetchToken();
  }, [dismissed]);

  const fetchToken = async () => {
    setLoadingToken(true);
    try {
      const { data } = await api.get<AgentTokenInfo[]>('/agent-tokens');
      const active = Array.isArray(data) ? data.find(t => t.is_active) : null;
      if (active) {
        setToken(active.token_prefix + '****');
      }
    } catch {
      // non-admin users can't list tokens, leave token empty
    } finally {
      setLoadingToken(false);
    }
  };

  const handleDismiss = () => {
    localStorage.setItem(DISMISSED_KEY, '1');
    setDismissed(true);
  };

  const serverUrl = `${window.location.protocol}//${window.location.hostname}:8001`;
  const tokenDisplay = token || '<YOUR_TOKEN>';
  const installCmd = `curl -fsSL ${serverUrl}/agent/install.sh | VIGILOPS_SERVER=${serverUrl} AGENT_TOKEN=${tokenDisplay} bash`;

  const copyToClipboard = () => {
    const text = token
      ? `curl -fsSL ${serverUrl}/agent/install.sh | VIGILOPS_SERVER=${serverUrl} AGENT_TOKEN=${tokenDisplay} bash`
      : installCmd;
    const succeed = () => {
      setCopied(true);
      messageApi.success(t('common.copied'));
      setTimeout(() => setCopied(false), 2000);
    };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(succeed).catch(() => fallbackCopy(text, succeed));
    } else {
      fallbackCopy(text, succeed);
    }
  };

  const fallbackCopy = (text: string, succeed: () => void) => {
    const el = document.createElement('textarea');
    el.value = text;
    el.style.cssText = 'position:fixed;top:-9999px;left:-9999px';
    document.body.appendChild(el);
    el.focus();
    el.select();
    try { document.execCommand('copy'); succeed(); } catch { messageApi.error(t('common.copyFailed')); }
    finally { document.body.removeChild(el); }
  };

  if (dismissed) return null;

  return (
    <>
      {contextHolder}
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message={
          <Space style={{ fontWeight: 600 }}>
            🚀 {t('agentBanner.title')}
          </Space>
        }
        description={
          <div>
            <Typography.Text style={{ display: 'block', marginBottom: 8 }}>
              {t('agentBanner.description')}
            </Typography.Text>
            {loadingToken ? (
              <Spin size="small" />
            ) : (
              <Space direction="vertical" style={{ width: '100%' }}>
                <div style={{
                  background: 'rgba(0,0,0,0.06)',
                  borderRadius: 6,
                  padding: '8px 12px',
                  fontFamily: 'monospace',
                  fontSize: 13,
                  wordBreak: 'break-all',
                }}>
                  {installCmd}
                </div>
                {!token && (
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {t('agentBanner.tokenHint')}
                  </Typography.Text>
                )}
                <Space>
                  <Button
                    size="small"
                    type="primary"
                    icon={copied ? <CheckOutlined /> : <CopyOutlined />}
                    onClick={copyToClipboard}
                  >
                    {copied ? t('common.copied') : t('common.copy')}
                  </Button>
                  <Button
                    size="small"
                    onClick={() => window.open('/settings', '_self')}
                  >
                    {t('agentBanner.manageTokens')}
                  </Button>
                </Space>
              </Space>
            )}
          </div>
        }
        closable
        closeIcon={<CloseOutlined />}
        onClose={handleDismiss}
      />
    </>
  );
}
