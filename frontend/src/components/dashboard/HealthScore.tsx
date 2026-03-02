/**
 * Dashboard 系统健康评分组件
 * 
 * 显示系统整体健康评分圆形进度条
 */
import React from 'react';
import { Card, Progress, Typography } from 'antd';

const { Text } = Typography;

interface HealthScoreProps {
  score: number;
}

const HealthScore: React.FC<HealthScoreProps> = ({ score }) => {
  // 根据评分确定颜色
  const getScoreColor = (score: number): string => {
    if (score >= 90) return '#52c41a'; // 绿色
    if (score >= 70) return '#faad14'; // 黄色
    if (score >= 50) return '#fa8c16'; // 橙色
    return '#ff4d4f'; // 红色
  };

  const scoreColor = getScoreColor(score);

  return (
    <Card style={{ textAlign: 'center' }}>
      <Text type="secondary" style={{ fontSize: 14 }}>
        健康评分
      </Text>
      <div style={{ marginTop: 8 }}>
        <Progress 
          type="circle" 
          percent={score} 
          size={100} 
          strokeColor={scoreColor}
          format={(p) => (
            <span style={{ color: scoreColor, fontWeight: 'bold', fontSize: 16 }}>
              {p}
            </span>
          )} 
        />
      </div>
    </Card>
  );
};

export default HealthScore;