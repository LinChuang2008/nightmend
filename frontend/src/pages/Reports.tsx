/**
 * 运维报告页面
 *
 * 包含报告列表视图和报告详情视图。
 * 支持生成日报/周报、查看详情、复制 Markdown 内容、删除报告。
 */
import { useEffect, useState, useCallback } from 'react';
import {
  Table, Button, Tag, Space, Modal, DatePicker, Typography, Card,
  Spin, message, Popconfirm, Descriptions,
} from 'antd';
import {
  PlusOutlined, EyeOutlined, DeleteOutlined, ArrowLeftOutlined,
  CopyOutlined, FileTextOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import type { Dayjs } from 'dayjs';
import {
  fetchReports, fetchReport, generateReport, deleteReport,
  type Report,
} from '../services/reports';
import { EmptyState, ErrorState, PageLoading } from '../components/StateComponents';
import PageHeader from '../components/PageHeader';

const { Title, Paragraph } = Typography;
const { RangePicker } = DatePicker;

/** 报告类型标签颜色映射 */
const typeColorMap: Record<string, string> = { daily: 'blue', weekly: 'purple' };
/** 报告类型中文映射 */
const typeLabelMap: Record<string, string> = { daily: '日报', weekly: '周报' };

/**
 * 简易 Markdown 渲染组件
 * 将 Markdown 文本按行解析为 Typography 组件
 */
function SimpleMarkdown({ content }: { content: string }) {
  if (!content) return <Paragraph type="secondary">暂无内容</Paragraph>;
  const lines = content.split('\n');
  return (
    <div>
      {lines.map((line, i) => {
        const trimmed = line.trimStart();
        if (trimmed.startsWith('### '))
          return <Title level={5} key={i} style={{ marginTop: 12 }}>{trimmed.slice(4)}</Title>;
        if (trimmed.startsWith('## '))
          return <Title level={4} key={i} style={{ marginTop: 16 }}>{trimmed.slice(3)}</Title>;
        if (trimmed.startsWith('# '))
          return <Title level={3} key={i} style={{ marginTop: 20 }}>{trimmed.slice(2)}</Title>;
        if (trimmed.startsWith('- ') || trimmed.startsWith('* '))
          return <Paragraph key={i} style={{ marginBottom: 4, paddingLeft: 16 }}>• {trimmed.slice(2)}</Paragraph>;
        if (trimmed === '') return <br key={i} />;
        return <Paragraph key={i} style={{ marginBottom: 4 }}>{line}</Paragraph>;
      })}
    </div>
  );
}

/** 运维报告页面组件 */
export default function Reports() {
  const [reports, setReports] = useState<Report[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<unknown>(null);
  /** 当前查看的报告详情（null 表示列表视图） */
  const [detail, setDetail] = useState<Report | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  /** 生成报告弹窗 */
  const [modalOpen, setModalOpen] = useState(false);
  const [modalType, setModalType] = useState<'daily' | 'weekly'>('daily');
  const [dateRange, setDateRange] = useState<[Dayjs, Dayjs] | null>(null);
  const [generating, setGenerating] = useState(false);

  /** 加载报告列表 */
  const loadReports = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const res = await fetchReports(page, pageSize);
      setReports(res.data.items || []);
      setTotal(res.data.total || 0);
    } catch (err) {
      setLoadError(err);
    } finally {
      setLoading(false);
    }
  }, [page, pageSize]);

  useEffect(() => { loadReports(); }, [loadReports]);

  /** 查看报告详情 */
  const handleView = async (id: number) => {
    setDetailLoading(true);
    try {
      const res = await fetchReport(id);
      setDetail(res.data);
    } catch {
      message.error('获取报告详情失败');
    } finally {
      setDetailLoading(false);
    }
  };

  /** 删除报告 */
  const handleDelete = async (id: number) => {
    try {
      await deleteReport(id);
      message.success('删除成功');
      loadReports();
    } catch {
      message.error('删除失败');
    }
  };

  /** 打开生成报告弹窗 */
  const openGenerateModal = (type: 'daily' | 'weekly') => {
    setModalType(type);
    if (type === 'daily') {
      const yesterday = dayjs().subtract(1, 'day');
      setDateRange([yesterday, yesterday]);
    } else {
      setDateRange([dayjs().subtract(1, 'week').startOf('week'), dayjs().subtract(1, 'week').endOf('week')]);
    }
    setModalOpen(true);
  };

  /** 提交生成报告请求 */
  const handleGenerate = async () => {
    if (!dateRange) return;
    setGenerating(true);
    try {
      await generateReport({
        report_type: modalType,
        period_start: dateRange[0].format('YYYY-MM-DD'),
        period_end: dateRange[1].format('YYYY-MM-DD'),
      });
      message.success('报告生成请求已提交');
      setModalOpen(false);
      loadReports();
    } catch {
      message.error('生成报告失败');
    } finally {
      setGenerating(false);
    }
  };

  /** 复制 Markdown 内容到剪贴板 */
  const handleCopy = async () => {
    if (!detail?.content) return;
    try {
      await navigator.clipboard.writeText(detail.content);
      message.success('已复制到剪贴板');
    } catch {
      message.error('复制失败');
    }
  };

  /** 状态标签渲染 */
  const renderStatus = (status: string) => {
    if (status === 'completed') return <Tag color="green">已完成</Tag>;
    if (status === 'generating') return <Tag icon={<Spin size="small" />} color="processing">生成中</Tag>;
    if (status === 'failed') return <Tag color="red">失败</Tag>;
    return <Tag>{status}</Tag>;
  };

  /** 表格列定义 */
  const columns = [
    { title: '标题', dataIndex: 'title', key: 'title', ellipsis: true },
    {
      title: '类型', dataIndex: 'report_type', key: 'report_type', width: 80,
      render: (t: string) => <Tag color={typeColorMap[t]}>{typeLabelMap[t] || t}</Tag>,
    },
    {
      title: '时间范围', key: 'period', width: 220,
      render: (_: unknown, r: Report) => `${dayjs(r.period_start).format('YYYY-MM-DD')} ~ ${dayjs(r.period_end).format('YYYY-MM-DD')}`,
    },
    { title: '状态', dataIndex: 'status', key: 'status', width: 100, render: renderStatus },
    {
      title: '生成时间', dataIndex: 'created_at', key: 'created_at', width: 180,
      render: (t: string) => dayjs(t).format('YYYY-MM-DD HH:mm:ss'),
    },
    {
      title: '操作', key: 'action', width: 150,
      render: (_: unknown, r: Report) => (
        <Space>
          <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => handleView(r.id)}>
            查看
          </Button>
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(r.id)}>
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  // ========== 详情视图 ==========
  if (detail || detailLoading) {
    return (
      <div>
        <Button icon={<ArrowLeftOutlined />} onClick={() => setDetail(null)} style={{ marginBottom: 16 }}>
          返回列表
        </Button>
        {detailLoading ? (
          <PageLoading tip="加载报告详情..." />
        ) : detail && (
          <Card>
            <Title level={4}><FileTextOutlined /> {detail.title}</Title>
            <Descriptions column={3} style={{ marginBottom: 16 }}>
              <Descriptions.Item label="类型">
                <Tag color={typeColorMap[detail.report_type]}>{typeLabelMap[detail.report_type] || detail.report_type}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="时间范围">{detail.period_start} ~ {detail.period_end}</Descriptions.Item>
              <Descriptions.Item label="生成时间">{dayjs(detail.created_at).format('YYYY-MM-DD HH:mm:ss')}</Descriptions.Item>
            </Descriptions>
            {detail.summary && (
              <Card type="inner" title="摘要" style={{ marginBottom: 16 }}>
                <Paragraph>{detail.summary}</Paragraph>
              </Card>
            )}
            <Card
              type="inner"
              title="报告内容"
              extra={<Button icon={<CopyOutlined />} onClick={handleCopy}>复制 Markdown</Button>}
            >
              <SimpleMarkdown content={detail.content} />
            </Card>
          </Card>
        )}
      </div>
    );
  }

  // ========== 列表视图 ==========
  return (
    <div>
      <PageHeader
        title="运维报告"
        extra={
          <Space>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => openGenerateModal('daily')}>
              生成日报
            </Button>
            <Button icon={<PlusOutlined />} onClick={() => openGenerateModal('weekly')}>
              生成周报
            </Button>
          </Space>
        }
      />

      {loadError ? (
        <ErrorState error={loadError} onRetry={loadReports} />
      ) : (
        <Table
          dataSource={reports}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            showTotal: (t) => `共 ${t} 条`,
            onChange: (p, ps) => { setPage(p); setPageSize(ps); },
          }}
          locale={{
            emptyText: <EmptyState scene="reports" onAction={() => openGenerateModal('daily')} />,
          }}
          scroll={{ x: 'max-content' }}
        />
      )}

      <Modal
        title={`生成${typeLabelMap[modalType]}`}
        open={modalOpen}
        onOk={handleGenerate}
        onCancel={() => setModalOpen(false)}
        confirmLoading={generating}
        okText="生成"
        cancelText="取消"
      >
        <div style={{ marginTop: 16 }}>
          <Typography.Text>选择时间范围：</Typography.Text>
          <div style={{ marginTop: 8 }}>
            <RangePicker
              value={dateRange}
              onChange={(v) => setDateRange(v as [Dayjs, Dayjs] | null)}
              style={{ width: '100%' }}
            />
          </div>
        </div>
      </Modal>
    </div>
  );
}
