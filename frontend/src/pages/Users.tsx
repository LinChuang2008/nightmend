/**
 * 用户管理页面
 *
 * 提供用户列表展示、新建/编辑/删除用户、重置密码、启用/禁用等功能。
 * 角色通过不同颜色 Tag 区分：admin=red, operator=blue, viewer=default。
 */
import { useEffect, useState } from 'react';
import { Table, Button, Tag, Switch, Modal, Form, Input, Select, Space, message, Popconfirm } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { useTranslation } from 'react-i18next';
import type { User, UserCreate, UserUpdate } from '../services/users';
import { fetchUsers, createUser, updateUser, deleteUser, resetPassword } from '../services/users';
import PageHeader from '../components/PageHeader';

/** 角色颜色映射 */
const roleColorMap: Record<string, string> = {
  admin: 'red',
  operator: 'blue',
  viewer: 'default',
};

export default function Users() {
  const { t } = useTranslation();
  const [users, setUsers] = useState<User[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);

  /** 新建/编辑弹窗 */
  const [modalOpen, setModalOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [form] = Form.useForm();

  /** 重置密码弹窗 */
  const [pwdModalOpen, setPwdModalOpen] = useState(false);
  const [pwdUserId, setPwdUserId] = useState<number | null>(null);
  const [pwdForm] = Form.useForm();

  const [messageApi, contextHolder] = message.useMessage();

  /** 角色选项 */
  const roleOptions = [
    { label: t('users.roles.admin'), value: 'admin' },
    { label: t('users.roles.operator'), value: 'operator' },
    { label: t('users.roles.viewer'), value: 'viewer' },
  ];

  /** 加载用户列表 */
  const load = async () => {
    setLoading(true);
    try {
      const { data } = await fetchUsers(page, pageSize);
      setUsers(data.items || []);
      setTotal(data.total || 0);
    } catch {
      messageApi.error(t('users.loadFailed'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [page]);

  /** 打开新建弹窗 */
  const handleCreate = () => {
    setEditingUser(null);
    form.resetFields();
    setModalOpen(true);
  };

  /** 打开编辑弹窗 */
  const handleEdit = (user: User) => {
    setEditingUser(user);
    form.setFieldsValue({ name: user.name, role: user.role });
    setModalOpen(true);
  };

  /** 提交新建/编辑表单 */
  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (editingUser) {
        await updateUser(editingUser.id, values as UserUpdate);
        messageApi.success(t('users.updated'));
      } else {
        await createUser(values as UserCreate);
        messageApi.success(t('users.created'));
      }
      setModalOpen(false);
      load();
    } catch {
      /* 表单校验失败或请求失败 */
    }
  };

  /** 切换用户启用/禁用状态 */
  const handleToggleActive = async (user: User, checked: boolean) => {
    try {
      await updateUser(user.id, { is_active: checked });
      messageApi.success(checked ? t('users.enabled') : t('users.disabled'));
      load();
    } catch {
      messageApi.error(t('users.actionFailed'));
    }
  };

  /** 删除用户 */
  const handleDelete = async (id: number) => {
    try {
      await deleteUser(id);
      messageApi.success(t('users.deleted'));
      load();
    } catch (err: any) {
      messageApi.error(err?.response?.data?.detail || t('users.deleteFailed'));
    }
  };

  /** 打开重置密码弹窗 */
  const handleResetPwd = (userId: number) => {
    setPwdUserId(userId);
    pwdForm.resetFields();
    setPwdModalOpen(true);
  };

  /** 提交重置密码 */
  const handlePwdSubmit = async () => {
    try {
      const { password } = await pwdForm.validateFields();
      if (pwdUserId !== null) {
        await resetPassword(pwdUserId, password);
        messageApi.success(t('users.passwordReset'));
        setPwdModalOpen(false);
      }
    } catch {
      /* ignore */
    }
  };

  const columns = [
    { title: t('users.email'), dataIndex: 'email', key: 'email' },
    { title: t('users.name'), dataIndex: 'name', key: 'name' },
    {
      title: t('users.role'),
      dataIndex: 'role',
      key: 'role',
      render: (role: string) => (
        <Tag color={roleColorMap[role] || 'default'}>{role}</Tag>
      ),
    },
    {
      title: t('users.status'),
      dataIndex: 'is_active',
      key: 'is_active',
      render: (active: boolean, record: User) => (
        <Switch checked={active} onChange={(v) => handleToggleActive(record, v)} />
      ),
    },
    {
      title: t('users.createdAt'),
      dataIndex: 'created_at',
      key: 'created_at',
      render: (v: string) => dayjs(v).format('YYYY-MM-DD HH:mm'),
    },
    {
      title: t('common.actions'),
      key: 'action',
      render: (_: unknown, record: User) => (
        <Space>
          <Button type="link" size="small" onClick={() => handleEdit(record)}>{t('common.edit')}</Button>
          <Button type="link" size="small" onClick={() => handleResetPwd(record.id)}>{t('users.resetPassword')}</Button>
          <Popconfirm title={t('users.confirmDeleteUser')} onConfirm={() => handleDelete(record.id)}>
            <Button type="link" size="small" danger>{t('common.delete')}</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <>
      {contextHolder}
      <PageHeader
        title={t('users.title')}
        extra={<Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>{t('users.createUser')}</Button>}
      />

      <Table
        rowKey="id"
        columns={columns}
        dataSource={users}
        loading={loading}
        pagination={{
          current: page,
          pageSize,
          total,
          onChange: (p) => setPage(p),
          showTotal: (count) => t('common.total', { count }),
        }}
      />

      {/* 新建/编辑用户弹窗 */}
      <Modal
        title={editingUser ? t('users.editUser') : t('users.newUser')}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          {!editingUser && (
            <>
              <Form.Item name="email" label={t('users.email')} rules={[{ required: true, type: 'email', message: t('users.emailRequired') }]}>
                <Input />
              </Form.Item>
              <Form.Item name="password" label={t('login.password')} rules={[{ required: true, min: 6, message: t('users.passwordMin') }]}>
                <Input.Password />
              </Form.Item>
            </>
          )}
          <Form.Item name="name" label={t('users.name')} rules={[{ required: true, message: t('users.nameRequired') }]}>
            <Input />
          </Form.Item>
          <Form.Item name="role" label={t('users.role')} rules={[{ required: true, message: t('users.roleRequired') }]}>
            <Select options={roleOptions} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 重置密码弹窗 */}
      <Modal
        title={t('users.resetPassword')}
        open={pwdModalOpen}
        onOk={handlePwdSubmit}
        onCancel={() => setPwdModalOpen(false)}
        destroyOnClose
      >
        <Form form={pwdForm} layout="vertical">
          <Form.Item name="password" label={t('users.newPassword')} rules={[{ required: true, min: 6, message: t('users.passwordMin') }]}>
            <Input.Password />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
