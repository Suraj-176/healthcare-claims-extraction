"""Database manager for extraction results and logs."""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import os


class DatabaseManager:
    """Manages SQLite database for extraction results and logs."""
    
    def __init__(self, db_path: str = None):
        """Initialize database manager.
        
        Args:
            db_path: Path to SQLite database file. Defaults to data/extractions.db
        """
        if db_path is None:
            # Store in data directory
            base_dir = Path(__file__).parent.parent.parent
            data_dir = base_dir / "data"
            data_dir.mkdir(exist_ok=True)
            db_path = str(data_dir / "extractions.db")
        
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """Initialize database with schema."""
        schema_path = Path(__file__).parent / "schema.sql"
        
        with sqlite3.connect(self.db_path) as conn:
            with open(schema_path, 'r') as f:
                conn.executescript(f.read())
            conn.commit()
    
    def save_extraction(
        self,
        filename: str,
        form_type: str,
        status: str,
        mean_confidence: float,
        cost: float,
        processing_time: float,
        llm_provider: str,
        result_json: Dict[Any, Any],
        image_path: str = None
    ) -> int:
        """Save extraction result to database.
        
        Returns:
            extraction_id: ID of saved extraction
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO extractions 
                (filename, form_type, status, mean_confidence, cost, 
                 processing_time, llm_provider, result_json, image_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                filename,
                form_type,
                status,
                mean_confidence,
                cost,
                processing_time,
                llm_provider,
                json.dumps(result_json, default=str),
                image_path
            ))
            conn.commit()
            return cursor.lastrowid
    
    def add_log(
        self,
        extraction_id: int,
        level: str,
        stage: str,
        message: str
    ):
        """Add processing log entry."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO logs (extraction_id, level, stage, message)
                VALUES (?, ?, ?, ?)
            """, (extraction_id, level, stage, message))
            conn.commit()
    
    def get_all_extractions(
        self,
        limit: int = 100,
        offset: int = 0,
        status_filter: str = None,
        form_type_filter: str = None,
        search_query: str = None
    ) -> List[Dict[str, Any]]:
        """Get all extraction results with optional filters."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            query = "SELECT * FROM extractions WHERE 1=1"
            params = []
            
            if status_filter:
                query += " AND status = ?"
                params.append(status_filter)
            
            if form_type_filter:
                query += " AND form_type = ?"
                params.append(form_type_filter)
            
            if search_query:
                query += " AND filename LIKE ?"
                params.append(f"%{search_query}%")
            
            query += " ORDER BY upload_date DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            return [dict(row) for row in rows]
    
    def get_extraction_by_id(self, extraction_id: int) -> Optional[Dict[str, Any]]:
        """Get single extraction by ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM extractions WHERE id = ?", (extraction_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_logs_for_extraction(self, extraction_id: int) -> List[Dict[str, Any]]:
        """Get all logs for an extraction."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM logs WHERE extraction_id = ? ORDER BY timestamp",
                (extraction_id,)
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def get_stats(self, days: int = 7) -> Dict[str, Any]:
        """Get statistics for dashboard.
        
        Args:
            days: Number of days to include in stats
            
        Returns:
            Dictionary with stats: total_files, avg_accuracy, avg_cost, success_rate
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Total files processed in period
            cursor.execute("""
                SELECT COUNT(*) FROM extractions 
                WHERE upload_date >= datetime('now', '-' || ? || ' days')
            """, (days,))
            total_files = cursor.fetchone()[0]
            
            # Average accuracy
            cursor.execute("""
                SELECT AVG(mean_confidence) FROM extractions 
                WHERE upload_date >= datetime('now', '-' || ? || ' days')
                AND status = 'ok'
            """, (days,))
            avg_accuracy = cursor.fetchone()[0] or 0
            
            # Average cost
            cursor.execute("""
                SELECT AVG(cost) FROM extractions 
                WHERE upload_date >= datetime('now', '-' || ? || ' days')
            """, (days,))
            avg_cost = cursor.fetchone()[0] or 0
            
            # Success rate
            cursor.execute("""
                SELECT 
                    COUNT(CASE WHEN status = 'ok' THEN 1 END) * 100.0 / COUNT(*) 
                FROM extractions 
                WHERE upload_date >= datetime('now', '-' || ? || ' days')
            """, (days,))
            success_rate = cursor.fetchone()[0] or 0
            
            return {
                'total_files': total_files,
                'avg_accuracy': avg_accuracy,
                'avg_cost': avg_cost,
                'success_rate': success_rate
            }
    
    def get_daily_stats(self, days: int = 7) -> List[Dict[str, Any]]:
        """Get daily statistics for charts."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    DATE(upload_date) as date,
                    COUNT(*) as count,
                    AVG(mean_confidence) as avg_accuracy,
                    AVG(cost) as avg_cost,
                    COUNT(CASE WHEN status = 'ok' THEN 1 END) as success_count
                FROM extractions
                WHERE upload_date >= datetime('now', '-' || ? || ' days')
                GROUP BY DATE(upload_date)
                ORDER BY date
            """, (days,))
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def get_form_type_distribution(self) -> Dict[str, int]:
        """Get distribution of form types."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT form_type, COUNT(*) as count
                FROM extractions
                GROUP BY form_type
            """)
            return {row[0]: row[1] for row in cursor.fetchall()}
    
    def get_setting(self, key: str) -> Optional[str]:
        """Get setting value."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row[0] if row else None
    
    def set_setting(self, key: str, value: str):
        """Set setting value."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            """, (key, value))
            conn.commit()
    
    def delete_extraction(self, extraction_id: int):
        """Delete extraction and its logs."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM logs WHERE extraction_id = ?", (extraction_id,))
            cursor.execute("DELETE FROM extractions WHERE id = ?", (extraction_id,))
            conn.commit()
    
    def clear_old_extractions(self, days: int = 30):
        """Clear extractions older than specified days."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM extractions 
                WHERE upload_date < datetime('now', '-' || ? || ' days')
            """, (days,))
            conn.commit()
