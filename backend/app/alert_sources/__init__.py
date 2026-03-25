"""
可插拔告警源适配器 (Pluggable Alert Source Adapters)

支持从多种外部告警系统接收告警并转化为 VigilOps RemediationAlert。
架构设计为可扩展的 adapter 模式，新增告警源只需实现 AlertSourceAdapter 接口。

当前支持:
- Prometheus AlertManager (webhook)

未来可扩展:
- Grafana OnCall
- PagerDuty
- 钉钉机器人
"""
