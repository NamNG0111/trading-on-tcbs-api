"""
Enhanced fast logging system with improved error handling and features
"""
import asyncio
import time
import os
from asyncio import Lock
from typing import Optional, List
from pathlib import Path


class FastLogger:
    """Enhanced asynchronous logging system with better error handling"""
    
    def __init__(self, path: str = 'log.txt', flush_interval: int = 5, max_buffer_size: int = 1000):
        self.buffer: List[str] = []
        self.path = Path(path)
        self.flush_interval = flush_interval
        self.max_buffer_size = max_buffer_size
        self.last_flush = time.time()
        self.lock = Lock()
        self._ensure_directory()
        
    def _ensure_directory(self) -> None:
        """Ensure the log directory exists"""
        self.path.parent.mkdir(parents=True, exist_ok=True)

    async def log(self, msg: str, level: str = "INFO") -> None:
        """
        Add message to log buffer with timestamp and level
        
        Args:
            msg: Message to log
            level: Log level (INFO, WARNING, ERROR, DEBUG)
        """
        timestamp = time.strftime('%H:%M:%S')
        formatted_msg = f"[{timestamp}] [{level}] {msg}"
        
        async with self.lock:
            self.buffer.append(formatted_msg)
            
            # Auto-flush if buffer is full or interval exceeded
            now = time.time()
            if (len(self.buffer) >= self.max_buffer_size or 
                now - self.last_flush >= self.flush_interval):
                await self._flush_locked()
                self.last_flush = now

    async def log_error(self, msg: str) -> None:
        """Log error message"""
        await self.log(msg, "ERROR")
        
    async def log_warning(self, msg: str) -> None:
        """Log warning message"""
        await self.log(msg, "WARNING")
        
    async def log_debug(self, msg: str) -> None:
        """Log debug message"""
        await self.log(msg, "DEBUG")

    async def flush(self) -> None:
        """Force flush log buffer to file"""
        async with self.lock:
            await self._flush_locked()
            self.last_flush = time.time()

    async def _flush_locked(self) -> None:
        """Internal flush method (assumes lock is held)"""
        if not self.buffer:
            return
            
        try:
            await asyncio.to_thread(self._write_to_file)
        except Exception as e:
            print(f"Error flushing log to {self.path}: {e}")

    def _write_to_file(self) -> None:
        """Write buffered messages to file (synchronous)"""
        try:
            with open(self.path, 'a', encoding='utf-8') as f:
                f.write('\n'.join(self.buffer) + '\n')
            self.buffer.clear()
        except Exception as e:
            print(f"Error writing to log file {self.path}: {e}")
            # Keep buffer for retry
            
    async def close(self) -> None:
        """Close logger and flush remaining messages"""
        await self.flush()
        
    def get_buffer_size(self) -> int:
        """Get current buffer size"""
        return len(self.buffer)
        
    def is_buffer_full(self) -> bool:
        """Check if buffer is at capacity"""
        return len(self.buffer) >= self.max_buffer_size


class LoggerManager:
    """Manages multiple loggers for different components"""
    
    def __init__(self, base_dir: str = "logs"):
        self.base_dir = Path(base_dir)
        self.loggers: dict[str, FastLogger] = {}
        self.base_dir.mkdir(exist_ok=True)
        
    def get_logger(self, name: str, subdir: Optional[str] = None, 
                   flush_interval: int = 5) -> FastLogger:
        """
        Get or create a logger for a specific component
        
        Args:
            name: Logger name
            subdir: Optional subdirectory
            flush_interval: Flush interval in seconds
            
        Returns:
            FastLogger instance
        """
        if name not in self.loggers:
            if subdir:
                log_path = self.base_dir / subdir / f"{name}.txt"
            else:
                log_path = self.base_dir / f"{name}.txt"
                
            self.loggers[name] = FastLogger(
                str(log_path), 
                flush_interval=flush_interval
            )
            
        return self.loggers[name]
        
    async def flush_all(self) -> None:
        """Flush all managed loggers"""
        tasks = [logger.flush() for logger in self.loggers.values()]
        await asyncio.gather(*tasks, return_exceptions=True)
        
    async def close_all(self) -> None:
        """Close all managed loggers"""
        tasks = [logger.close() for logger in self.loggers.values()]
        await asyncio.gather(*tasks, return_exceptions=True)
        self.loggers.clear()


# Global logger manager instance
logger_manager = LoggerManager()


def get_logger(name: str, subdir: Optional[str] = None) -> FastLogger:
    """
    Convenience function to get a logger
    
    Args:
        name: Logger name
        subdir: Optional subdirectory
        
    Returns:
        FastLogger instance
    """
    return logger_manager.get_logger(name, subdir)
