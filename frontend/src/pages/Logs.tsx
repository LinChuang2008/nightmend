/**
 * 日志管理页面
 *
 * 提供两种模式：
 * 1. 搜索模式 - 按关键字、服务器、服务、日志级别、时间范围筛选日志，支持分页
 * 2. 实时模式 - 通过 WebSocket 实时接收并展示日志流，支持暂停/继续和清空
 */
import { useEffect, useState, useRef, useCallback } from 'react';
import { useResponsive } from '../hooks/useResponsive';
import {
  Input, Select, DatePicker, Table, Tag, Row, Col, Button, Space, Drawer, Descriptions, Typography, Segmented, Tooltip,
} from 'antd';
import {
  SearchOutlined, PauseCircleOutlined, PlayCircleOutlined, ClearOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import dayjs, { Dayjs } from 'dayjs';
import { fetchLogs } from '../services/logs';
import type { LogEntry, LogQueryParams } from '../services/logs';
import api from '../services/api';

const { RangePicker } = DatePicker;
const { Title, Text } = Typography;

const LEVEL_COLOR: Record<string, string> = {
  DEBUG: 'default',
  INFO: 'blue',
  WARN: 'orange',
  ERROR: 'red',
  FATAL: 'purple',
};

const LEVELS = ['DEBUG', 'INFO', 'WARN', 'ERROR', 'FATAL'];

export default function Logs() {
  const { t } = useTranslation();
  const { isMobile } = useResponsive();
  const [keyword, setKeyword] = useState('');
  const [hostId, setHostId] = useState<string | undefined>();
  const [service, setService] = useState<string | undefined>();
  const [levels, setLevels] = useState<string[]>([]);
  const [timeRange, setTimeRange] = useState<[Dayjs | null, Dayjs | null] | null>(null);

  const [data, setData] = useState<LogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [loading, setLoading] = useState(false);

  const [hostOptions, setHostOptions] = useState<{ label: string; value: string }[]>([]);
  const [serviceOptions, setServiceOptions] = useState<{ label: string; value: string }[]>([]);
  const hostMapRef = useRef<Record<string, string>>({});

  const [mode, setMode] = useState<string>('search');

  const [drawerVisible, setDrawerVisible] = useState(false);
  const [selectedLog, setSelectedLog] = useState<LogEntry | null>(null);
  const [contextLogs, setContextLogs] = useState<LogEntry[]>([]);
  const [contextLoading, setContextLoading] = useState(false);

  const [realtimeLogs, setRealtimeLogs] = useState<LogEntry[]>([]);
  const [paused, setPaused] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const realtimeEndRef = useRef<HTMLDivElement>(null);
  const pausedRef = useRef(false);

  useEffect(() => {
    api.get('/hosts', { params: { page_size: 100 } }).then(res => {
      const items = res.data.items || [];
      const opts = items.map((h: { id: number; hostname: string }) => ({ label: h.hostname, value: String(h.id) }));
      setHostOptions(opts);
      const map: Record<string, string> = {};
      items.forEach((h: { id: number; hostname: string }) => { map[String(h.id)] = h.hostname; });
      hostMapRef.current = map;
    }).catch(() => {});
    api.get('/services', { params: { page_size: 100 } }).then(res => {
      const items = res.data.items || [];
      const names = [...new Set(items.map((s: { name: string }) => s.name))] as string[];
      setServiceOptions(names.map(n => ({ label: n, value: n })));
    }).catch(() => {});
  }, []);

  const doFetch = useCallback(async () => {
    setLoading(true);
    try {
      const params: LogQueryParams = { keyword, host_id: hostId, service, level: levels.length ? levels : undefined, page, page_size: pageSize };
      if (timeRange && timeRange[0]) params.start_time = timeRange[0].toISOString();
      if (timeRange && timeRange[1]) params.end_time = timeRange[1].toISOString();
      const res = await fetchLogs(params);
      setData(res.items || []);
      setTotal(res.total || 0);
    } catch { /* ignore */ } finally {
      setLoading(false);
    }
  }, [keyword, hostId, service, levels, timeRange, page, pageSize]);

  useEffect(() => {
    if (mode === 'search') doFetch();
  }, [mode, doFetch]);

  useEffect(() => {
    if (mode !== 'realtime') {
      wsRef.current?.close();
      wsRef.current = null;
      return;
    }
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const params = new URLSearchParams();
    const token = localStorage.getItem('token') || '';
    if (token) params.set('token', token);
    if (hostId) params.set('host_id', hostId);
    if (service) params.set('service', service);
    if (levels.length) params.set('level', levels.join(','));
    if (keyword) params.set('keyword', keyword);
    const url = `${proto}://${window.location.host}/ws/logs?${params.toString()}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;
    setRealtimeLogs([]);

    ws.onmessage = (evt) => {
      if (pausedRef.current) return;
      try {
        const entry: LogEntry = JSON.parse(evt.data);
        setRealtimeLogs(prev => {
          const next = [...prev, entry];
          return next.length > 500 ? next.slice(next.length - 500) : next;
        });
      } catch { /* ignore */ }
    };
    ws.onerror = () => {};
    ws.onclose = () => {};

    return () => { ws.close(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, hostId, service, levels, keyword]);

  useEffect(() => {
    if (mode === 'realtime' && !paused) {
      realtimeEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [realtimeLogs, mode, paused]);

  const togglePause = () => {
    setPaused(p => { pausedRef.current = !p; return !p; });
  };

  const openDrawer = async (log: LogEntry) => {
    setSelectedLog(log);
    setDrawerVisible(true);
    setContextLoading(true);
    try {
      const ts = dayjs(log.timestamp);
      const params: LogQueryParams = {
        start_time: ts.subtract(5, 'minute').toISOString(),
        end_time: ts.add(5, 'minute').toISOString(),
        host_id: log.host_id,
        service: log.service,
        page_size: 21,
      };
      const res = await fetchLogs(params);
      setContextLogs(res.items || []);
    } catch { setContextLogs([]); } finally { setContextLoading(false); }
  };

  const columns = [
    { title: t('logs.timestamp'), dataIndex: 'timestamp', key: 'timestamp', width: 180, render: (val: string) => dayjs(val).format('YYYY-MM-DD HH:mm:ss') },
    { title: t('logs.server'), dataIndex: 'hostname', key: 'hostname', width: 140, render: (name: string, record: LogEntry) => name || hostMapRef.current[String(record.host_id)] || `Host #${record.host_id}` },
    { title: t('logs.service'), dataIndex: 'service', key: 'service', width: 120 },
    { title: t('logs.level'), dataIndex: 'level', key: 'level', width: 90, render: (l: string) => <Tag color={LEVEL_COLOR[l] || 'default'}>{l}</Tag> },
    { title: t('logs.message'), dataIndex: 'message', key: 'message', ellipsis: true },
  ];

  return (
    <div>
      <Row justify="space-between" align="middle" style={{ marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>{t('logs.title')}</Title>
        <Segmented
          options={[
            { label: t('logs.searchMode'), value: 'search' },
            { label: t('logs.realtimeLogs'), value: 'realtime' },
          ]}
          value={mode}
          onChange={v => setMode(v as string)}
        />
      </Row>

      <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
        <Col xs={24} sm={12} md={6}>
          <Input.Search
            placeholder={t('logs.search')}
            allowClear
            prefix={<SearchOutlined />}
            value={keyword}
            onChange={e => setKeyword(e.target.value)}
            onSearch={() => { if (mode === 'search') { setPage(1); doFetch(); } }}
          />
        </Col>
        <Col xs={12} sm={6} md={4}>
          <Select placeholder={t('logs.server')} allowClear style={{ width: '100%' }} options={hostOptions} value={hostId} onChange={setHostId} showSearch optionFilterProp="label" />
        </Col>
        <Col xs={12} sm={6} md={4}>
          <Select placeholder={t('logs.service')} allowClear style={{ width: '100%' }} options={serviceOptions} value={service} onChange={setService} showSearch optionFilterProp="label" />
        </Col>
        <Col xs={24} sm={12} md={5}>
          <Select mode="multiple" placeholder={t('logs.levelFilter')} allowClear style={{ width: '100%' }} options={LEVELS.map(l => ({ label: l, value: l }))} value={levels} onChange={setLevels} />
        </Col>
        {mode === 'search' && (
          <Col xs={24} sm={12} md={5}>
            <RangePicker showTime style={{ width: '100%' }} value={timeRange as [Dayjs, Dayjs] | null} onChange={(v) => setTimeRange(v)} />
          </Col>
        )}
      </Row>

      {mode === 'search' && (
        <Table
          dataSource={data}
          columns={columns}
          rowKey="id"
          loading={loading}
          size="small"
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            showTotal: (tot) => t('common.total', { count: tot }),
            onChange: (p, ps) => { setPage(p); setPageSize(ps); },
          }}
          onRow={(record) => ({ onClick: () => openDrawer(record), style: { cursor: 'pointer' } })}
        />
      )}

      {mode === 'realtime' && (
        <div>
          <Space style={{ marginBottom: 8 }}>
            <Tooltip title={paused ? t('logs.resumed') : t('logs.paused')}>
              <Button icon={paused ? <PlayCircleOutlined /> : <PauseCircleOutlined />} onClick={togglePause}>
                {paused ? t('logs.resumed') : t('logs.paused')}
              </Button>
            </Tooltip>
            <Button icon={<ClearOutlined />} onClick={() => setRealtimeLogs([])}>{t('logs.clear')}</Button>
            <Text type="secondary">{realtimeLogs.length} {t('common.times')}</Text>
          </Space>
          <div style={{
            background: '#1e1e1e', color: '#d4d4d4', fontFamily: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
            fontSize: 13, lineHeight: 1.6, padding: 16, borderRadius: 8, height: 500, overflowY: 'auto',
          }}>
            {realtimeLogs.map((log, i) => (
              <div key={`${log.id || i}`} style={{ cursor: 'pointer' }} onClick={() => openDrawer(log)}>
                <span style={{ color: '#888' }}>{dayjs(log.timestamp).format('HH:mm:ss.SSS')}</span>
                {' '}
                <span style={{ color: { DEBUG: '#888', INFO: '#4fc1ff', WARN: '#cca700', ERROR: '#f44747', FATAL: '#c586c0' }[log.level] || '#d4d4d4' }}>
                  [{log.level}]
                </span>
                {' '}
                <span style={{ color: '#9cdcfe' }}>{hostMapRef.current[String(log.host_id)] || `Host#${log.host_id}`}/{log.service}</span>
                {' '}
                <span>{log.message}</span>
              </div>
            ))}
            <div ref={realtimeEndRef} />
          </div>
        </div>
      )}

      <Drawer
        title={t('logs.logDetail')}
        open={drawerVisible}
        onClose={() => setDrawerVisible(false)}
        width={isMobile ? '100%' : 640}
      >
        {selectedLog && (
          <>
            <Descriptions column={1} bordered size="small" style={{ marginBottom: 16 }}>
              <Descriptions.Item label={t('logs.timestamp')}>{dayjs(selectedLog.timestamp).format('YYYY-MM-DD HH:mm:ss.SSS')}</Descriptions.Item>
              <Descriptions.Item label={t('logs.server')}>{selectedLog.hostname}</Descriptions.Item>
              <Descriptions.Item label={t('logs.service')}>{selectedLog.service}</Descriptions.Item>
              <Descriptions.Item label={t('logs.level')}><Tag color={LEVEL_COLOR[selectedLog.level]}>{selectedLog.level}</Tag></Descriptions.Item>
              {selectedLog.file_path && <Descriptions.Item label={t('logs.filePath')}>{selectedLog.file_path}</Descriptions.Item>}
            </Descriptions>

            <Title level={5}>{t('logs.messageContent')}</Title>
            <pre style={{ background: '#f5f5f5', padding: 12, borderRadius: 6, whiteSpace: 'pre-wrap', wordBreak: 'break-all', maxHeight: 200, overflow: 'auto' }}>
              {selectedLog.message}
            </pre>

            <Title level={5} style={{ marginTop: 16 }}>{t('logs.contextLogs')}</Title>
            <Table
              dataSource={contextLogs}
              columns={columns}
              rowKey={(r, i) => r.id || String(i)}
              loading={contextLoading}
              size="small"
              pagination={false}
              rowClassName={(record) => record.id === selectedLog.id ? 'ant-table-row-selected' : ''}
            />
          </>
        )}
      </Drawer>
    </div>
  );
}
