"""物料申请审批流程 - 可迭代的材料数据空间（M3-02 G2.2）。

提供物料新增/修改/删除的申请-审批闭环：
- save: 提交申请（status=SUBMITTED）
- get: 按 request_id 获取
- list_all / list_pending: 查询列表
- update_status: 更新审批状态
"""

from __future__ import annotations
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime, timezone
import json
import uuid
import logging

from sqlalchemy import text

from ..db import get_engine
from ..mdm.reference_dict import ReferenceDictStore

logger = logging.getLogger(__name__)


def _iso(value) -> str:
    """将 datetime 或字符串转换为 ISO 字符串；None 返回空字符串。"""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class RequestStatus(str, Enum):
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    WRITTEN = "written"  # 已写入物料库


class MaterialRequest(BaseModel):
    """物料申请单。"""
    request_id: str = ""
    material_data: dict  # 申请的物料数据
    request_type: str = "add"  # add / update / delete
    requester: str = ""
    status: RequestStatus = RequestStatus.SUBMITTED
    submitted_at: str = ""
    reviewed_by: str = ""
    reviewed_at: str = ""
    review_comment: str = ""


class MaterialRequestStore:
    """物料申请单的 PostgreSQL 持久化存储。"""

    # 写入物料库前需校验的必填字段
    REQUIRED_FIELDS = ['name', 'formula']

    def __init__(self, db_path: str | None = None):
        # db_path 参数保留以兼容旧调用方，迁移至 PostgreSQL 后已忽略，统一使用全局 Engine。
        self.engine = get_engine()
        self._mdm = ReferenceDictStore()

    def _row_to_request(self, row) -> MaterialRequest:
        return MaterialRequest(
            request_id=row[0],
            material_data=row[1] or {},
            request_type=row[2] or "add",
            requester=row[3] or "",
            status=RequestStatus(row[4]) if row[4] else RequestStatus.SUBMITTED,
            submitted_at=_iso(row[5]),
            reviewed_by=row[6] or "",
            reviewed_at=_iso(row[7]),
            review_comment=row[8] or "",
        )

    def _validate_status(self, status: RequestStatus) -> None:
        """校验 status 必须存在于 MDM status_codes（domain='material_request'）中。"""
        mdm_code = self._mdm.get_status_code(domain="material_request", code=status.value)
        if mdm_code is None:
            raise ValueError(f"无效的状态值: {status.value}")

    def validate_material_data(self, material_data: dict) -> dict | None:
        """校验物料数据必填字段（approve 写入物料库前调用）。

        Returns:
            None 表示校验通过；否则返回 {"error": ...}。
        """
        for field in self.REQUIRED_FIELDS:
            if not material_data.get(field):
                return {"error": f"物料数据缺少必填字段: {field}"}
        return None

    def save(self, request: MaterialRequest) -> MaterialRequest:
        """保存申请单（新增或更新）。自动生成 request_id 与 submitted_at。"""
        if not request.request_id:
            request.request_id = f"MR-{uuid.uuid4().hex[:8].upper()}"
        if not request.submitted_at:
            request.submitted_at = datetime.now(timezone.utc).isoformat()

        self._validate_status(request.status)

        with self.engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO industrialization.material_requests
                (request_id, material_data, request_type, requester, status,
                 submitted_at, reviewed_by, reviewed_at, review_comment)
                VALUES (:request_id, CAST(:material_data AS JSONB), :request_type, :requester, :status,
                        :submitted_at, :reviewed_by, :reviewed_at, :review_comment)
                ON CONFLICT (request_id) DO UPDATE SET
                    material_data=EXCLUDED.material_data,
                    request_type=EXCLUDED.request_type,
                    requester=EXCLUDED.requester,
                    status=EXCLUDED.status,
                    submitted_at=EXCLUDED.submitted_at,
                    reviewed_by=EXCLUDED.reviewed_by,
                    reviewed_at=EXCLUDED.reviewed_at,
                    review_comment=EXCLUDED.review_comment"""),
                {
                    "request_id": request.request_id,
                    "material_data": json.dumps(request.material_data, ensure_ascii=False),
                    "request_type": request.request_type,
                    "requester": request.requester,
                    "status": request.status.value,
                    "submitted_at": request.submitted_at,
                    "reviewed_by": request.reviewed_by,
                    "reviewed_at": request.reviewed_at,
                    "review_comment": request.review_comment,
                },
            )
        return request

    def get(self, request_id: str) -> MaterialRequest | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM industrialization.material_requests WHERE request_id=:request_id"),
                {"request_id": request_id},
            ).fetchone()
        return self._row_to_request(row) if row else None

    def list_all(self) -> list[MaterialRequest]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT * FROM industrialization.material_requests ORDER BY submitted_at DESC")
            ).fetchall()
        return [self._row_to_request(r) for r in rows]

    def list_pending(self) -> list[MaterialRequest]:
        """列出待审批的申请（status=submitted）。"""
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT * FROM industrialization.material_requests WHERE status=:status "
                     "ORDER BY submitted_at DESC"),
                {"status": RequestStatus.SUBMITTED.value},
            ).fetchall()
        return [self._row_to_request(r) for r in rows]

    def update_status(
        self, request_id: str, status: RequestStatus,
        reviewed_by: str = "", review_comment: str = "",
    ) -> MaterialRequest | None:
        """更新审批状态，记录审批人与审批时间。"""
        self._validate_status(status)
        now = datetime.now(timezone.utc).isoformat()
        with self.engine.begin() as conn:
            conn.execute(
                text("""UPDATE industrialization.material_requests
                   SET status=:status, reviewed_by=:reviewed_by, reviewed_at=:reviewed_at, review_comment=:review_comment
                   WHERE request_id=:request_id"""),
                {
                    "status": status.value, "reviewed_by": reviewed_by,
                    "reviewed_at": now, "review_comment": review_comment,
                    "request_id": request_id,
                },
            )
        return self.get(request_id)


# 全局单例
_request_store: MaterialRequestStore | None = None


def get_request_store() -> MaterialRequestStore:
    global _request_store
    if _request_store is None:
        _request_store = MaterialRequestStore()
    return _request_store
