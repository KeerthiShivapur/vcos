"""Tests for WAL Archive Monitor service."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.wal_archive_monitor import (
    WALArchiveMonitor,
    WALArchiveHealthReport,
    WALArchiveHealthState,
    WALSegmentInfo,
    WALSegmentState,
)


class TestWALArchiveHealthReport:
    """Test WALArchiveHealthReport serialization."""
    
    def test_report_creation(self):
        """Test creating a health report."""
        report = WALArchiveHealthReport(
            report_id="wal-health-test",
            generated_at=datetime.now(timezone.utc),
            overall_state=WALArchiveHealthState.HEALTHY,
            archive_mode="on",
            archive_command="test command",
            archiving_process_state="HEALTHY",
            latest_archived_segment="00000001000000890000001E",
            latest_segment_hash="a" * 64,
            latest_segment_hash_verified=True,
            new_archive_failures=0,
            historical_failures_present=False,
            total_failed_count=0,
            continuous_chain_from_baseline=True,
            baseline_segment="000000010000008900000015",
            verified_wal_range_start="000000010000008900000015",
            verified_wal_range_end="00000001000000890000001E",
            ready_files_count=0,
            done_files_count=5,
            accumulating_ready_files=False,
            stale_archiving_activity=False,
            last_archive_time=datetime.now(timezone.utc) - timedelta(minutes=1),
            archive_lag_minutes=1.0,
            max_allowed_lag_minutes=5,
            physical_backup_verified=True,
            restore_test_verified=True,
            pitr_test_verified=True,
            overall_recovery_readiness="READY",
        )
        
        assert report.report_id == "wal-health-test"
        assert report.overall_state == WALArchiveHealthState.HEALTHY
        assert report.archiving_process_state == "HEALTHY"
        assert report.continuous_chain_from_baseline is True
        assert report.overall_recovery_readiness == "READY"
    
    def test_report_to_dict(self):
        """Test report serialization to dict."""
        now = datetime.now(timezone.utc)
        report = WALArchiveHealthReport(
            report_id="wal-health-dict",
            generated_at=now,
            overall_state=WALArchiveHealthState.DEGRADED,
            archive_mode="on",
            new_archive_failures=2,
            historical_failures_present=True,
            total_failed_count=10,
            last_failed_wal="000000010000008900000014",
            last_failed_time=now - timedelta(hours=2),
            continuous_chain_from_baseline=False,
            missing_historical_segments=["000000010000008900000014"],
            ready_files_count=5,
            accumulating_ready_files=True,
            archive_lag_minutes=10.0,
            max_allowed_lag_minutes=5,
            physical_backup_verified=False,
            restore_test_verified=False,
            pitr_test_verified=False,
            overall_recovery_readiness="NOT_READY",
            alerts=[
                {"level": "CRITICAL", "code": "NEW_ARCHIVE_FAILURES", "message": "2 new failures"},
                {"level": "WARNING", "code": "ARCHIVE_LAG_HIGH", "message": "Lag 10 min > 5 min"},
            ],
        )
        
        data = report.to_dict()
        
        assert data["report_id"] == "wal-health-dict"
        assert data["overall_state"] == "degraded"
        assert data["new_archive_failures"] == 2
        assert data["historical_failures_present"] is True
        assert data["total_failed_count"] == 10
        assert data["last_failed_wal"] == "000000010000008900000014"
        assert data["continuous_chain_from_baseline"] is False
        assert data["missing_historical_segments"] == ["000000010000008900000014"]
        assert data["accumulating_ready_files"] is True
        assert data["archive_lag_minutes"] == 10.0
        assert data["overall_recovery_readiness"] == "NOT_READY"
        assert len(data["alerts"]) == 2
        assert data["alerts"][0]["level"] == "CRITICAL"
        assert data["alerts"][1]["level"] == "WARNING"
    
    def test_report_to_json(self):
        """Test JSON serialization."""
        report = WALArchiveHealthReport(
            report_id="wal-health-json",
            generated_at=datetime.now(timezone.utc),
            overall_state=WALArchiveHealthState.UNHEALTHY,
        )
        
        json_str = report.to_json()
        assert isinstance(json_str, str)
        assert "wal-health-json" in json_str
        assert "unhealthy" in json_str


class TestWALSegmentInfo:
    """Test WALSegmentInfo."""
    
    def test_segment_info_creation(self):
        """Test creating segment info."""
        segment = WALSegmentInfo(
            segment_name="00000001000000890000001E",
            state=WALSegmentState.ARCHIVED,
            size_bytes=16777216,
            expected_size_bytes=16777216,
            hash_sha256="a" * 64,
            archive_time=datetime.now(timezone.utc),
            retry_count=0,
            location="archive",
        )
        
        assert segment.segment_name == "00000001000000890000001E"
        assert segment.state == WALSegmentState.ARCHIVED
        assert segment.size_bytes == 16777216
        assert segment.hash_sha256 == "a" * 64
        assert segment.location == "archive"
    
    def test_segment_states(self):
        """Test segment state enum."""
        assert WALSegmentState.ARCHIVED.value == "archived"
        assert WALSegmentState.PENDING.value == "pending"
        assert WALSegmentState.FAILED.value == "failed"
        assert WALSegmentState.MISSING.value == "missing"
        assert WALSegmentState.CORRUPT.value == "corrupt"
        assert WALSegmentState.UNKNOWN.value == "unknown"


class TestWALArchiveMonitor:
    """Test WALArchiveMonitor service."""
    
    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        return AsyncMock()
    
    @pytest.fixture
    def monitor(self):
        """Create monitor instance."""
        return WALArchiveMonitor()
    
    @pytest.mark.asyncio
    async def test_initialize(self, monitor, mock_db):
        """Test monitor initialization."""
        # Mock detector
        monitor.detector = MagicMock()
        monitor.detector.db = mock_db
        monitor.detector.detect = AsyncMock(return_value=True)
        
        # Mock db.execute for baseline capture
        mock_archiver = MagicMock()
        mock_archiver.archived_count = 100
        mock_archiver.failed_count = 5
        mock_archiver.last_failed_wal = "000000010000008900000014"
        mock_archiver.last_failed_time = datetime.now(timezone.utc) - timedelta(hours=1)
        
        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_archiver
        mock_db.execute = AsyncMock(return_value=mock_result)
        
        await monitor.initialize(mock_db)
        
        assert monitor._historical_failure_baseline == 5
        assert monitor._last_known_archived_count == 100
    
    @pytest.mark.asyncio
    async def test_check_health_no_pitr(self, monitor, mock_db):
        """Test health check when PITR not available."""
        monitor.detector = MagicMock()
        monitor.detector.db = mock_db
        monitor.detector.detect = AsyncMock(return_value=False)
        
        report = await monitor.check_health(mock_db)
        
        assert report.overall_state == WALArchiveHealthState.UNKNOWN
        assert any(a["code"] == "PITR_UNAVAILABLE" for a in report.alerts)
    
    @pytest.mark.asyncio
    async def test_check_health_archive_mode_off(self, monitor, mock_db):
        """Test health check when archive_mode is off."""
        monitor.detector = MagicMock()
        monitor.detector.db = mock_db
        monitor.detector.detect = AsyncMock(return_value=True)
        
        # Mock archive_mode = off
        mock_result = MagicMock()
        mock_result.scalar.return_value = "off"
        mock_db.execute = AsyncMock(return_value=mock_result)
        
        report = await monitor.check_health(mock_db)
        
        assert report.overall_state == WALArchiveHealthState.UNHEALTHY
        assert report.archiving_process_state == "FAILED"
        assert report.archive_mode == "off"
        assert any(a["code"] == "ARCHIVE_MODE_OFF" for a in report.alerts)
    
    @pytest.mark.asyncio
    async def test_check_health_healthy(self, monitor, mock_db):
        """Test health check when everything is healthy."""
        monitor.detector = MagicMock()
        monitor.detector.db = mock_db
        monitor.detector.detect = AsyncMock(return_value=True)
        
        # Mock archive_mode = on
        mock_archive_mode = MagicMock()
        mock_archive_mode.scalar.return_value = "on"
        
        # Mock archive_command
        mock_archive_command = MagicMock()
        mock_archive_command.scalar.return_value = "test command"
        
        # Mock pg_stat_archiver - use fetchone to return a proper object
        mock_archiver_row = MagicMock()
        mock_archiver_row.archived_count = 100
        mock_archiver_row.last_archived_wal = "00000001000000890000001E"
        mock_archiver_row.last_archived_time = datetime.now(timezone.utc) - timedelta(minutes=1)
        mock_archiver_row.failed_count = 5
        mock_archiver_row.last_failed_wal = "000000010000008900000014"
        mock_archiver_row.last_failed_time = datetime.now(timezone.utc) - timedelta(hours=1)
        mock_archiver_row.stats_reset = datetime.now(timezone.utc) - timedelta(days=1)
        
        mock_archiver_result = MagicMock()
        mock_archiver_result.fetchone.return_value = mock_archiver_row
        
        # Sequence of execute calls
        mock_db.execute = AsyncMock(side_effect=[
            mock_archive_mode,      # SHOW archive_mode
            mock_archive_command,   # SHOW archive_command
            mock_archiver_result,   # pg_stat_archiver
        ])
        
        # Mock historical baseline
        monitor._historical_failure_baseline = 5
        monitor._last_known_archived_count = 100
        
        report = await monitor.check_health(mock_db)
        
        assert report.overall_state == WALArchiveHealthState.HEALTHY
        assert report.archiving_process_state == "HEALTHY"
        assert report.archive_mode == "on"
        assert report.latest_archived_segment == "00000001000000890000001E"
        assert report.total_failed_count == 5
        assert report.new_archive_failures == 0  # Same as baseline
        assert report.historical_failures_present is True
        assert report.archive_lag_minutes is not None
        assert report.archive_lag_minutes < 5  # Within threshold
        assert report.stale_archiving_activity is False
    
    @pytest.mark.asyncio
    async def test_check_health_new_failures(self, monitor, mock_db):
        """Test health check detects new failures."""
        monitor.detector = MagicMock()
        monitor.detector.db = mock_db
        monitor.detector.detect = AsyncMock(return_value=True)
        
        mock_archive_mode = MagicMock()
        mock_archive_mode.scalar.return_value = "on"
        
        mock_archive_command = MagicMock()
        mock_archive_command.scalar.return_value = "test command"
        
        # pg_stat_archiver with new failures
        mock_archiver_row = MagicMock()
        mock_archiver_row.archived_count = 105
        mock_archiver_row.last_archived_wal = "00000001000000890000001F"
        mock_archiver_row.last_archived_time = datetime.now(timezone.utc) - timedelta(minutes=1)
        mock_archiver_row.failed_count = 8  # 3 new failures since baseline of 5
        mock_archiver_row.last_failed_wal = "00000001000000890000001D"
        mock_archiver_row.last_failed_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        
        mock_archiver_result = MagicMock()
        mock_archiver_result.fetchone.return_value = mock_archiver_row
        
        mock_db.execute = AsyncMock(side_effect=[
            mock_archive_mode,
            mock_archive_command,
            mock_archiver_result,
        ])
        
        monitor._historical_failure_baseline = 5
        monitor._last_known_archived_count = 100
        
        report = await monitor.check_health(mock_db)
        
        assert report.new_archive_failures == 3
        assert report.total_failed_count == 8
        assert any(a["code"] == "NEW_ARCHIVE_FAILURES" for a in report.alerts)
        # Should be degraded due to new failures
        assert report.overall_state in (WALArchiveHealthState.DEGRADED, WALArchiveHealthState.UNHEALTHY)
    
    @pytest.mark.asyncio
    async def test_check_health_stale_archiving(self, monitor, mock_db):
        """Test health check detects stale archiving."""
        monitor.detector = MagicMock()
        monitor.detector.db = mock_db
        monitor.detector.detect = AsyncMock(return_value=True)
        
        mock_archive_mode = MagicMock()
        mock_archive_mode.scalar.return_value = "on"
        
        mock_archive_command = MagicMock()
        mock_archive_command.scalar.return_value = "test command"
        
        # pg_stat_archiver with stale archiving
        mock_archiver_row = MagicMock()
        mock_archiver_row.archived_count = 100
        mock_archiver_row.last_archived_wal = "00000001000000890000001E"
        mock_archiver_row.last_archived_time = datetime.now(timezone.utc) - timedelta(minutes=15)  # 15 min ago
        mock_archiver_row.failed_count = 5
        mock_archiver_row.last_failed_wal = "000000010000008900000014"
        mock_archiver_row.last_failed_time = datetime.now(timezone.utc) - timedelta(hours=1)
        
        mock_archiver_result = MagicMock()
        mock_archiver_result.fetchone.return_value = mock_archiver_row
        
        mock_db.execute = AsyncMock(side_effect=[
            mock_archive_mode,
            mock_archive_command,
            mock_archiver_result,
        ])
        
        monitor._historical_failure_baseline = 5
        monitor._last_known_archived_count = 100
        
        report = await monitor.check_health(mock_db)
        
        assert report.archive_lag_minutes is not None
        assert report.archive_lag_minutes > 5  # Exceeds default threshold
        assert report.stale_archiving_activity is True
        assert any(a["code"] == "ARCHIVE_LAG_HIGH" for a in report.alerts)
    
    @pytest.mark.asyncio
    async def test_verify_segment_hash(self, monitor, mock_db):
        """Test segment hash verification."""
        # This test would need actual files - skip for unit test
        pass
    
    def test_compute_sha256(self, monitor, tmp_path):
        """Test SHA-256 computation."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")
        
        hash_result = monitor._compute_sha256(str(test_file))
        
        assert len(hash_result) == 64  # SHA-256 hex length
        # Known hash for "hello world"
        assert hash_result == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])