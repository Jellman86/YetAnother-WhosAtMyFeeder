"""Media cache service for storing snapshots and clips locally."""

import os
import asyncio
import aiofiles
import aiofiles.os
import structlog
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

log = structlog.get_logger()

# Cache directory structure
CACHE_BASE_DIR = Path("/config/media_cache")
SNAPSHOTS_DIR = CACHE_BASE_DIR / "snapshots"
CLIPS_DIR = CACHE_BASE_DIR / "clips"


class MediaCacheService:
    """Manages local caching of snapshots and clips from Frigate.

    Cache files are named by event_id for easy lookup.
    File modification time is used for retention-based cleanup.
    """

    def __init__(self):
        self._ensure_dirs()

    def _ensure_dirs(self):
        """Ensure cache directories exist."""
        SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        CLIPS_DIR.mkdir(parents=True, exist_ok=True)

    def _snapshot_path(self, event_id: str) -> Path:
        """Get the path for a cached snapshot."""
        # Sanitize event_id to prevent path traversal
        safe_id = "".join(c for c in event_id if c.isalnum() or c in "-_.")
        return SNAPSHOTS_DIR / f"{safe_id}.jpg"

    def _clip_path(self, event_id: str) -> Path:
        """Get the path for a cached clip."""
        safe_id = "".join(c for c in event_id if c.isalnum() or c in "-_.")
        return CLIPS_DIR / f"{safe_id}.mp4"

    async def cache_snapshot(self, event_id: str, image_bytes: bytes) -> Optional[Path]:
        """Cache a snapshot image.

        Args:
            event_id: Frigate event ID
            image_bytes: JPEG image data

        Returns:
            Path to cached file, or None if caching failed
        """
        try:
            path = self._snapshot_path(event_id)
            async with aiofiles.open(path, 'wb') as f:
                await f.write(image_bytes)
            log.debug("Cached snapshot", event_id=event_id, size=len(image_bytes))
            return path
        except Exception as e:
            log.error("Failed to cache snapshot", event_id=event_id, error=str(e))
            return None

    async def get_snapshot(self, event_id: str) -> Optional[bytes]:
        """Get a cached snapshot.

        Args:
            event_id: Frigate event ID

        Returns:
            Image bytes if cached, None otherwise
        """
        try:
            path = self._snapshot_path(event_id)
            if await aiofiles.os.path.exists(path):
                async with aiofiles.open(path, 'rb') as f:
                    data = await f.read()
                # Update access time for LRU-like behavior
                os.utime(path, None)
                return data
            return None
        except Exception as e:
            log.error("Failed to read cached snapshot", event_id=event_id, error=str(e))
            return None

    def has_snapshot(self, event_id: str) -> bool:
        """Check if a snapshot is cached (sync version for quick checks)."""
        return self._snapshot_path(event_id).exists()

    async def cache_clip(self, event_id: str, clip_bytes: bytes) -> Optional[Path]:
        """Cache a video clip.

        Args:
            event_id: Frigate event ID
            clip_bytes: MP4 video data

        Returns:
            Path to cached file, or None if caching failed
        """
        try:
            path = self._clip_path(event_id)
            async with aiofiles.open(path, 'wb') as f:
                await f.write(clip_bytes)
            log.debug("Cached clip", event_id=event_id, size=len(clip_bytes))
            return path
        except Exception as e:
            log.error("Failed to cache clip", event_id=event_id, error=str(e))
            return None

    async def cache_clip_streaming(self, event_id: str, chunks) -> Optional[Path]:
        """Cache a video clip from a stream of chunks.

        Args:
            event_id: Frigate event ID
            chunks: Async iterator of bytes chunks

        Returns:
            Path to cached file, or None if caching failed or file is empty
        """
        try:
            path = self._clip_path(event_id)
            total_size = 0
            async with aiofiles.open(path, 'wb') as f:
                async for chunk in chunks:
                    if chunk:
                        await f.write(chunk)
                        total_size += len(chunk)
            
            if total_size == 0:
                log.warning("Downloaded empty clip (0 bytes)", event_id=event_id)
                # Clean up empty file
                try:
                    if path.exists():
                        path.unlink()
                except:
                    pass
                return None

            log.debug("Cached clip (streaming)", event_id=event_id, size=total_size)
            return path
        except Exception as e:
            log.error("Failed to cache clip", event_id=event_id, error=str(e))
            # Clean up partial file
            try:
                path = self._clip_path(event_id)
                if path.exists():
                    path.unlink()
            except:
                pass
            return None

    def get_clip_path(self, event_id: str) -> Optional[Path]:
        """Get path to a cached clip if it exists and has content.

        Args:
            event_id: Frigate event ID

        Returns:
            Path to cached clip, or None if not cached or empty
        """
        path = self._clip_path(event_id)
        if path.exists():
            # Check that file has content (not 0 bytes from failed download)
            if path.stat().st_size > 0:
                # Update access time
                os.utime(path, None)
                return path
            else:
                # Remove empty/corrupt file so it will be refetched
                try:
                    path.unlink()
                    log.warning("Removed empty cached clip", event_id=event_id)
                except:
                    pass
        return None

    def has_clip(self, event_id: str) -> bool:
        """Check if a clip is cached and has content."""
        path = self._clip_path(event_id)
        return path.exists() and path.stat().st_size > 0

    async def delete_cached_media(self, event_id: str):
        """Delete all cached media for an event.

        Args:
            event_id: Frigate event ID
        """
        try:
            snapshot_path = self._snapshot_path(event_id)
            if await aiofiles.os.path.exists(snapshot_path):
                await aiofiles.os.remove(snapshot_path)

            clip_path = self._clip_path(event_id)
            if await aiofiles.os.path.exists(clip_path):
                await aiofiles.os.remove(clip_path)

            log.debug("Deleted cached media", event_id=event_id)
        except Exception as e:
            log.error("Failed to delete cached media", event_id=event_id, error=str(e))

    async def cleanup_empty_files(self) -> dict:
        """Delete empty/corrupt cached files (0-byte files).

        Returns:
            Dict with cleanup stats
        """
        stats = {"snapshots_deleted": 0, "clips_deleted": 0}

        # Clean empty snapshots
        for path in SNAPSHOTS_DIR.glob("*.jpg"):
            try:
                if path.stat().st_size == 0:
                    path.unlink()
                    stats["snapshots_deleted"] += 1
                    log.debug("Removed empty snapshot", path=str(path))
            except FileNotFoundError:
                pass # Already deleted
            except Exception as e:
                log.warning("Failed to delete empty snapshot", path=str(path), error=str(e))

        # Clean empty clips
        for path in CLIPS_DIR.glob("*.mp4"):
            try:
                if path.stat().st_size == 0:
                    path.unlink()
                    stats["clips_deleted"] += 1
                    log.debug("Removed empty clip", path=str(path))
            except FileNotFoundError:
                pass # Already deleted
            except Exception as e:
                log.warning("Failed to delete empty clip", path=str(path), error=str(e))

        if stats["snapshots_deleted"] > 0 or stats["clips_deleted"] > 0:
            log.info("Empty file cleanup complete", **stats)
        return stats

    async def cleanup_old_media(self, retention_days: int) -> dict:
        """Delete cached media older than retention period.

        Args:
            retention_days: Delete files older than this many days

        Returns:
            Dict with cleanup stats
        """
        # Always clean up empty/corrupt files first
        empty_stats = await self.cleanup_empty_files()

        if retention_days <= 0:
            return {
                "snapshots_deleted": empty_stats["snapshots_deleted"],
                "clips_deleted": empty_stats["clips_deleted"],
                "bytes_freed": 0
            }

        cutoff = datetime.now() - timedelta(days=retention_days)
        cutoff_timestamp = cutoff.timestamp()

        stats = {
            "snapshots_deleted": empty_stats["snapshots_deleted"],
            "clips_deleted": empty_stats["clips_deleted"],
            "bytes_freed": 0
        }

        # Clean old snapshots
        for path in SNAPSHOTS_DIR.glob("*.jpg"):
            try:
                if path.stat().st_mtime < cutoff_timestamp:
                    size = path.stat().st_size
                    path.unlink()
                    stats["snapshots_deleted"] += 1
                    stats["bytes_freed"] += size
            except Exception as e:
                log.warning("Failed to delete old snapshot", path=str(path), error=str(e))

        # Clean old clips
        for path in CLIPS_DIR.glob("*.mp4"):
            try:
                if path.stat().st_mtime < cutoff_timestamp:
                    size = path.stat().st_size
                    path.unlink()
                    stats["clips_deleted"] += 1
                    stats["bytes_freed"] += size
            except Exception as e:
                log.warning("Failed to delete old clip", path=str(path), error=str(e))

        log.info("Media cache cleanup complete", **stats)
        return stats

    async def cleanup_orphaned_media(self, valid_event_ids: set[str]) -> dict:
        """Delete cached media for events that no longer exist in DB.

        Args:
            valid_event_ids: Set of event IDs that still exist

        Returns:
            Dict with cleanup stats
        """
        stats = {"snapshots_deleted": 0, "clips_deleted": 0, "bytes_freed": 0}

        # Clean orphaned snapshots
        for path in SNAPSHOTS_DIR.glob("*.jpg"):
            event_id = path.stem
            if event_id not in valid_event_ids:
                try:
                    size = path.stat().st_size
                    path.unlink()
                    stats["snapshots_deleted"] += 1
                    stats["bytes_freed"] += size
                except Exception as e:
                    log.warning("Failed to delete orphaned snapshot", path=str(path), error=str(e))

        # Clean orphaned clips
        for path in CLIPS_DIR.glob("*.mp4"):
            event_id = path.stem
            if event_id not in valid_event_ids:
                try:
                    size = path.stat().st_size
                    path.unlink()
                    stats["clips_deleted"] += 1
                    stats["bytes_freed"] += size
                except Exception as e:
                    log.warning("Failed to delete orphaned clip", path=str(path), error=str(e))

        log.info("Orphaned media cleanup complete", **stats)
        return stats

    def get_cache_stats(self) -> dict:
        """Get cache statistics.

        Returns:
            Dict with cache stats
        """
        snapshot_count = 0
        snapshot_size = 0
        clip_count = 0
        clip_size = 0
        oldest_file = None
        newest_file = None

        for path in SNAPSHOTS_DIR.glob("*.jpg"):
            try:
                stat = path.stat()
                snapshot_count += 1
                snapshot_size += stat.st_size
                mtime = datetime.fromtimestamp(stat.st_mtime)
                if oldest_file is None or mtime < oldest_file:
                    oldest_file = mtime
                if newest_file is None or mtime > newest_file:
                    newest_file = mtime
            except:
                pass

        for path in CLIPS_DIR.glob("*.mp4"):
            try:
                stat = path.stat()
                clip_count += 1
                clip_size += stat.st_size
                mtime = datetime.fromtimestamp(stat.st_mtime)
                if oldest_file is None or mtime < oldest_file:
                    oldest_file = mtime
                if newest_file is None or mtime > newest_file:
                    newest_file = mtime
            except:
                pass

        return {
            "snapshot_count": snapshot_count,
            "snapshot_size_bytes": snapshot_size,
            "snapshot_size_mb": round(snapshot_size / (1024 * 1024), 2),
            "clip_count": clip_count,
            "clip_size_bytes": clip_size,
            "clip_size_mb": round(clip_size / (1024 * 1024), 2),
            "total_size_bytes": snapshot_size + clip_size,
            "total_size_mb": round((snapshot_size + clip_size) / (1024 * 1024), 2),
            "oldest_file": oldest_file.isoformat() if oldest_file else None,
            "newest_file": newest_file.isoformat() if newest_file else None,
        }


# Global singleton
media_cache = MediaCacheService()
