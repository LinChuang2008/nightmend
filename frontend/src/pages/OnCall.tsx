/**
 * 值班排期管理页面
 *
 * 包含三个 Tab：
 * 1. 值班组 - 值班组 CRUD 管理
 * 2. 排期管理 - 排期 CRUD + 冲突检测
 * 3. 值班日历 - 日历视图展示排期
 */
import { useEffect, useState, useCallback, useMemo } from 'react';
import { useResponsive } from '../hooks/useResponsive';
import {
  Card, Table, Button, Modal, Form, Input, Switch, Select, Tag, Space, Tabs,
  message, Popconfirm, DatePicker, Typography, Badge, Calendar,
} from 'antd';
import type { Dayjs } from 'dayjs';
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined,
  TeamOutlined, CalendarOutlined, CheckCircleOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { useTranslation } from 'react-i18next';
import { onCallService } from '../services/onCall';

const { Title, Text } = Typography;

interface OnCallGroup {
  id: number;
  name: string;
  description: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

interface OnCallSchedule {
  id: number;
  group_id: number;
  user_id: number;
  start_date: string;
  end_date: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

interface CurrentOnCall {
  user_id: number;
  email: string;
  group_id: number;
  group_name: string;
  schedule_id: number;
  start_date: string;
  end_date: string;
}

interface CoverageData {
  total_schedules: number;
  schedules: Array<{
    schedule_id: number;
    user_id: number;
    email: string;
    group_id: number;
    group_name: string;
    start_date: string;
    end_date: string;
  }>;
  coverage_analysis: {
    coverage_rate: number;
    covered_days: number;
    total_days: number;
    has_gaps: boolean;
  };
}

export default function OnCall() {
  const { isMobile } = useResponsive();
  const { t } = useTranslation();
  const [messageApi, contextHolder] = message.useMessage();

  // ===== 值班组 =====
  const [groups, setGroups] = useState<OnCallGroup[]>([]);
  const [groupsTotal, setGroupsTotal] = useState(0);
  const [groupsPage, setGroupsPage] = useState(1);
  const [groupsLoading, setGroupsLoading] = useState(false);
  const [groupModalOpen, setGroupModalOpen] = useState(false);
  const [editingGroup, setEditingGroup] = useState<OnCallGroup | null>(null);
  const [groupForm] = Form.useForm();

  // ===== 排期 =====
  const [schedules, setSchedules] = useState<OnCallSchedule[]>([]);
  const [schedulesTotal, setSchedulesTotal] = useState(0);
  const [schedulesPage, setSchedulesPage] = useState(1);
  const [schedulesLoading, setSchedulesLoading] = useState(false);
  const [scheduleModalOpen, setScheduleModalOpen] = useState(false);
  const [editingSchedule, setEditingSchedule] = useState<OnCallSchedule | null>(null);
  const [scheduleForm] = Form.useForm();
  const [filterGroupId, setFilterGroupId] = useState<number | undefined>();

  // ===== 当前值班 =====
  const [currentOnCall, setCurrentOnCall] = useState<CurrentOnCall | null>(null);

  // ===== 日历 =====
  const [calendarMonth, setCalendarMonth] = useState(dayjs());
  const [coverageData, setCoverageData] = useState<CoverageData | null>(null);
  const [coverageLoading, setCoverageLoading] = useState(false);

  // ===== 用户列表 (for select) =====
  const [users, setUsers] = useState<Array<{ id: number; email: string }>>([]);

  // ===== 数据加载 =====
  const fetchGroups = useCallback(async () => {
    setGroupsLoading(true);
    try {
      const { data } = await onCallService.listGroups({ page: groupsPage, page_size: 20 });
      setGroups(data.items || []);
      setGroupsTotal(data.total || 0);
    } catch { /* ignore */ } finally { setGroupsLoading(false); }
  }, [groupsPage]);

  const fetchSchedules = useCallback(async () => {
    setSchedulesLoading(true);
    try {
      const params: Record<string, unknown> = { page: schedulesPage, page_size: 20 };
      if (filterGroupId) params.group_id = filterGroupId;
      const { data } = await onCallService.listSchedules(params);
      setSchedules(data.items || []);
      setSchedulesTotal(data.total || 0);
    } catch { /* ignore */ } finally { setSchedulesLoading(false); }
  }, [schedulesPage, filterGroupId]);

  const fetchCurrentOnCall = useCallback(async () => {
    try {
      const { data } = await onCallService.getCurrentOnCall();
      setCurrentOnCall(data);
    } catch { /* ignore */ }
  }, []);

  const fetchCoverage = useCallback(async () => {
    setCoverageLoading(true);
    try {
      const start = calendarMonth.startOf('month').format('YYYY-MM-DD');
      const end = calendarMonth.endOf('month').format('YYYY-MM-DD');
      const { data } = await onCallService.getCoverage(start, end);
      // 确保 schedules 字段始终是数组，防止 useMemo 崩溃
      setCoverageData(data ? { ...data, schedules: Array.isArray(data.schedules) ? data.schedules : [] } : null);
    } catch { /* ignore */ } finally { setCoverageLoading(false); }
  }, [calendarMonth]);

  const fetchUsers = useCallback(async () => {
    try {
      // Use a simple approach - fetch from users API
      const token = localStorage.getItem('token');
      const resp = await fetch('/api/v1/users?page_size=100', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (resp.ok) {
        const data = await resp.json();
        setUsers((data.items || []).map((u: any) => ({ id: u.id, email: u.email })));
      }
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { fetchGroups(); }, [fetchGroups]);
  useEffect(() => { fetchSchedules(); }, [fetchSchedules]);
  useEffect(() => { fetchCurrentOnCall(); }, [fetchCurrentOnCall]);
  useEffect(() => { fetchCoverage(); }, [fetchCoverage]);
  useEffect(() => { fetchUsers(); }, [fetchUsers]);

  // ===== 值班组 CRUD =====
  const openGroupModal = (group?: OnCallGroup) => {
    setEditingGroup(group || null);
    if (group) {
      groupForm.setFieldsValue(group);
    } else {
      groupForm.resetFields();
      groupForm.setFieldsValue({ is_active: true });
    }
    setGroupModalOpen(true);
  };

  const handleGroupSave = async () => {
    try {
      const values = await groupForm.validateFields();
      if (editingGroup) {
        await onCallService.updateGroup(editingGroup.id, values);
        messageApi.success(t('onCall.groupUpdated'));
      } else {
        await onCallService.createGroup(values);
        messageApi.success(t('onCall.groupCreated'));
      }
      setGroupModalOpen(false);
      fetchGroups();
    } catch { /* validation error */ }
  };

  const handleGroupDelete = async (id: number) => {
    try {
      await onCallService.deleteGroup(id);
      messageApi.success(t('onCall.groupDeleted'));
      fetchGroups();
    } catch { messageApi.error(t('onCall.deleteFailed')); }
  };

  // ===== 排期 CRUD =====
  const openScheduleModal = (schedule?: OnCallSchedule) => {
    setEditingSchedule(schedule || null);
    if (schedule) {
      scheduleForm.setFieldsValue({
        ...schedule,
        dateRange: [dayjs(schedule.start_date), dayjs(schedule.end_date)],
      });
    } else {
      scheduleForm.resetFields();
      scheduleForm.setFieldsValue({ is_active: true });
    }
    setScheduleModalOpen(true);
  };

  const handleScheduleSave = async () => {
    try {
      const values = await scheduleForm.validateFields();
      const payload = {
        group_id: values.group_id,
        user_id: values.user_id,
        start_date: values.dateRange[0].format('YYYY-MM-DD'),
        end_date: values.dateRange[1].format('YYYY-MM-DD'),
        is_active: values.is_active ?? true,
      };
      if (editingSchedule) {
        await onCallService.updateSchedule(editingSchedule.id, payload);
        messageApi.success(t('onCall.scheduleUpdated'));
      } else {
        await onCallService.createSchedule(payload);
        messageApi.success(t('onCall.scheduleCreated'));
      }
      setScheduleModalOpen(false);
      fetchSchedules();
      fetchCoverage();
      fetchCurrentOnCall();
    } catch (err: any) {
      if (err?.response?.data?.detail) {
        messageApi.error(err.response.data.detail);
      }
    }
  };

  const handleScheduleDelete = async (id: number) => {
    try {
      await onCallService.deleteSchedule(id);
      messageApi.success(t('onCall.scheduleDeleted'));
      fetchSchedules();
      fetchCoverage();
    } catch { messageApi.error(t('onCall.deleteFailed')); }
  };

  // ===== 日历渲染 =====
  const schedulesByDate = useMemo(() => {
    if (!coverageData) return {};
    const map: Record<string, Array<{ email: string; group_name: string }>> = {};
    for (const s of (coverageData.schedules ?? [])) {
      let cur = dayjs(s.start_date);
      const end = dayjs(s.end_date);
      while (cur.isBefore(end) || cur.isSame(end, 'day')) {
        const key = cur.format('YYYY-MM-DD');
        if (!map[key]) map[key] = [];
        map[key].push({ email: s.email, group_name: s.group_name });
        cur = cur.add(1, 'day');
      }
    }
    return map;
  }, [coverageData]);

  const dateCellRender = (value: Dayjs) => {
    const key = value.format('YYYY-MM-DD');
    const items = schedulesByDate[key];
    if (!items || items.length === 0) return null;
    return (
      <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
        {items.slice(0, 3).map((item, idx) => (
          <li key={idx}>
            <Badge
              status="success"
              text={<Text style={{ fontSize: 12 }}>{item.email} ({item.group_name})</Text>}
            />
          </li>
        ))}
        {items.length > 3 && (
          <li><Text type="secondary" style={{ fontSize: 11 }}>{t('onCall.moreItems', { count: items.length - 3 })}</Text></li>
        )}
      </ul>
    );
  };

  // ===== 组名映射 =====
  const groupNameMap = useMemo(() => {
    const map: Record<number, string> = {};
    groups.forEach(g => { map[g.id] = g.name; });
    return map;
  }, [groups]);

  const userNameMap = useMemo(() => {
    const map: Record<number, string> = {};
    users.forEach(u => { map[u.id] = u.email; });
    return map;
  }, [users]);

  // ===== 表格列 =====
  const groupColumns = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    { title: t('onCall.columnName'), dataIndex: 'name', ellipsis: true },
    { title: t('onCall.columnDesc'), dataIndex: 'description', ellipsis: true },
    {
      title: t('onCall.columnStatus'), dataIndex: 'is_active', width: 80,
      render: (v: boolean) => <Tag color={v ? 'green' : 'default'}>{v ? t('onCall.columnActive') : t('onCall.columnInactive')}</Tag>,
    },
    {
      title: t('onCall.columnCreatedAt'), dataIndex: 'created_at', width: 170,
      render: (v: string) => dayjs(v).format('YYYY-MM-DD HH:mm'),
    },
    {
      title: t('onCall.columnActions'), width: 120, fixed: 'right' as const,
      render: (_: unknown, record: OnCallGroup) => (
        <Space>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openGroupModal(record)} />
          <Popconfirm title={t('onCall.confirmDeleteGroup')} onConfirm={() => handleGroupDelete(record.id)}>
            <Button type="link" size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const scheduleColumns = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    {
      title: t('onCall.columnGroup'), dataIndex: 'group_id', width: 120,
      render: (v: number) => groupNameMap[v] || t('onCall.groupIdPrefix', { id: v }),
    },
    {
      title: t('onCall.columnPerson'), dataIndex: 'user_id', width: 120,
      render: (v: number) => userNameMap[v] || t('onCall.userIdPrefix', { id: v }),
    },
    {
      title: t('onCall.columnPeriod'), width: 220,
      render: (_: unknown, r: OnCallSchedule) => `${r.start_date} ~ ${r.end_date}`,
    },
    {
      title: t('onCall.columnStatus'), dataIndex: 'is_active', width: 80,
      render: (v: boolean) => <Tag color={v ? 'green' : 'default'}>{v ? t('onCall.columnActive') : t('onCall.columnInactive')}</Tag>,
    },
    {
      title: t('onCall.columnActions'), width: 120, fixed: 'right' as const,
      render: (_: unknown, record: OnCallSchedule) => (
        <Space>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openScheduleModal(record)} />
          <Popconfirm title={t('onCall.confirmDeleteSchedule')} onConfirm={() => handleScheduleDelete(record.id)}>
            <Button type="link" size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <>
      {contextHolder}
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Title level={4} style={{ margin: 0 }}>{t('onCall.title')}</Title>
        {currentOnCall && (
          <Card size="small" style={{ background: '#f6ffed', border: '1px solid #b7eb8f' }}>
            <Space>
              <CheckCircleOutlined style={{ color: '#52c41a' }} />
              <Text strong>{t('onCall.currentOnCall')}</Text>
              <Text>{currentOnCall.email}</Text>
              <Tag color="blue">{currentOnCall.group_name}</Tag>
              <Text type="secondary">{currentOnCall.start_date} ~ {currentOnCall.end_date}</Text>
            </Space>
          </Card>
        )}
      </div>

      <Tabs
        items={[
          {
            key: 'groups',
            label: <span><TeamOutlined /> {t('onCall.groups')}</span>,
            children: (
              <Card
                extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => openGroupModal()}>{t('onCall.newGroup')}</Button>}
              >
                <Table
                  rowKey="id"
                  columns={groupColumns}
                  dataSource={groups}
                  loading={groupsLoading}
                  pagination={{ current: groupsPage, total: groupsTotal, pageSize: 20, onChange: setGroupsPage }}
                  scroll={{ x: 700 }}
                  size="small"
                />
              </Card>
            ),
          },
          {
            key: 'schedules',
            label: <span><CalendarOutlined /> {t('onCall.scheduleManage')}</span>,
            children: (
              <Card
                extra={
                  <Space>
                    <Select
                      style={{ width: isMobile ? '100%' : 160 }}
                      placeholder={t('onCall.filterGroup')}
                      allowClear
                      value={filterGroupId}
                      onChange={(v) => { setFilterGroupId(v); setSchedulesPage(1); }}
                      options={groups.map(g => ({ value: g.id, label: g.name }))}
                    />
                    <Button type="primary" icon={<PlusOutlined />} onClick={() => openScheduleModal()}>{t('onCall.newSchedule')}</Button>
                    <Button icon={<ReloadOutlined />} onClick={fetchSchedules} />
                  </Space>
                }
              >
                <Table
                  rowKey="id"
                  columns={scheduleColumns}
                  dataSource={schedules}
                  loading={schedulesLoading}
                  pagination={{ current: schedulesPage, total: schedulesTotal, pageSize: 20, onChange: setSchedulesPage }}
                  scroll={{ x: 750 }}
                  size="small"
                />
              </Card>
            ),
          },
          {
            key: 'calendar',
            label: <span><CalendarOutlined /> {t('onCall.calendar')}</span>,
            children: (
              <Card
                loading={coverageLoading}
                extra={
                  <Space>
                    {coverageData?.coverage_analysis && (
                      <Tag
                        color={coverageData.coverage_analysis.has_gaps ? 'warning' : 'success'}
                        icon={coverageData.coverage_analysis.has_gaps ? <WarningOutlined /> : <CheckCircleOutlined />}
                      >
                        {t('onCall.coverageRate')}{(coverageData.coverage_analysis.coverage_rate * 100).toFixed(0)}%
                        ({coverageData.coverage_analysis.covered_days}/{coverageData.coverage_analysis.total_days}{t('onCall.dayUnit')})
                      </Tag>
                    )}
                    <Button icon={<ReloadOutlined />} onClick={fetchCoverage} />
                  </Space>
                }
              >
                <Calendar
                  cellRender={(date, info) => {
                    if (info.type === 'date') return dateCellRender(date);
                    return null;
                  }}
                  onPanelChange={(date) => setCalendarMonth(date)}
                />
              </Card>
            ),
          },
        ]}
      />

      {/* 值班组编辑弹窗 */}
      <Modal
        title={editingGroup ? t('onCall.editGroup') : t('onCall.newGroupTitle')}
        open={groupModalOpen}
        onOk={handleGroupSave}
        onCancel={() => setGroupModalOpen(false)}
        destroyOnClose
      >
        <Form form={groupForm} layout="vertical">
          <Form.Item name="name" label={t('onCall.groupNameLabel')} rules={[{ required: true, message: t('onCall.groupNameRequired') }]}>
            <Input placeholder={t('onCall.groupNamePlaceholder')} />
          </Form.Item>
          <Form.Item name="description" label={t('onCall.descLabel')}>
            <Input.TextArea rows={3} placeholder={t('onCall.descPlaceholder')} />
          </Form.Item>
          <Form.Item name="is_active" label={t('onCall.activeLabel')} valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      {/* 排期编辑弹窗 */}
      <Modal
        title={editingSchedule ? t('onCall.editSchedule') : t('onCall.newScheduleTitle')}
        open={scheduleModalOpen}
        onOk={handleScheduleSave}
        onCancel={() => setScheduleModalOpen(false)}
        destroyOnClose
      >
        <Form form={scheduleForm} layout="vertical">
          <Form.Item name="group_id" label={t('onCall.columnGroup')} rules={[{ required: true, message: t('onCall.groupRequired') }]}>
            <Select
              placeholder={t('onCall.filterGroup')}
              options={groups.filter(g => g.is_active).map(g => ({ value: g.id, label: g.name }))}
            />
          </Form.Item>
          <Form.Item name="user_id" label={t('onCall.columnPerson')} rules={[{ required: true, message: t('onCall.personRequired') }]}>
            <Select
              placeholder={t('onCall.columnPerson')}
              showSearch
              optionFilterProp="label"
              options={users.map(u => ({ value: u.id, label: u.email }))}
            />
          </Form.Item>
          <Form.Item name="dateRange" label={t('onCall.columnPeriod')} rules={[{ required: true, message: t('onCall.periodRequired') }]}>
            <DatePicker.RangePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="is_active" label={t('onCall.activeLabel')} valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
