"""异常扫描服务测试。"""


class TestAnomalyScanner:
    async def test_import_scanner(self):
        from app.services.anomaly_scanner import scan_recent_logs
        assert callable(scan_recent_logs)

    async def test_import_loop(self):
        from app.services.anomaly_scanner import anomaly_scanner_loop
        assert callable(anomaly_scanner_loop)
