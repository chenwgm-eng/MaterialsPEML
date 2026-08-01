"""0034: external_invocations 新增完整输入快照列

T-032：LLM 调用输入快照完整化。
- integrations.external_invocations 新增 input_full_json TEXT 列（可空）
  存放完整输入快照（prompt + 上下文 + 全部参数），用于审计回溯。
  使用 TEXT 而非 JSONB：审计需求优先于存储优化，且避免对大字段建 GIN 索引。
- 新增 model_version TEXT 列（可空），明确记录 LLM 调用所用模型版本。
- 现有 input_redacted_json / input_sha256 保留不变，用于快速统计。

Revision ID: 0034_external_invocations_input_full
Revises: 0033_candidate_content_hash
"""

from alembic import op

revision = "0034_external_invocations_input_full"
down_revision = "0033_candidate_content_hash"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE integrations.external_invocations "
        "ADD COLUMN IF NOT EXISTS input_full_json TEXT"
    )
    op.execute(
        "ALTER TABLE integrations.external_invocations "
        "ADD COLUMN IF NOT EXISTS model_version TEXT"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE integrations.external_invocations "
        "DROP COLUMN IF EXISTS model_version"
    )
    op.execute(
        "ALTER TABLE integrations.external_invocations "
        "DROP COLUMN IF EXISTS input_full_json"
    )
