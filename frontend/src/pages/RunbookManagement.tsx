import { Card, Typography } from 'antd';
import PageHeader from '../components/PageHeader';

export default function RunbookManagement() {
  return (
    <div>
      <PageHeader title="Runbook 管理" />
      <Card>
        <Typography.Text type="secondary">
          当前环境未启用 Runbook 编辑依赖，功能已临时下线。
        </Typography.Text>
      </Card>
    </div>
  );
}

