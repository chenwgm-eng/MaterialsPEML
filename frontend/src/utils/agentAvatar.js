/**
 * 智能体头像统一解析：后端内置智能体使用 emoji 作为 avatar 字段。
 * 前端统一映射为 antd 语义图标，避免 emoji 作为功能性图标（Anti-AI-Slop P0）。
 */
import {
  RobotOutlined,
  ExperimentOutlined,
  CalculatorOutlined,
  BarChartOutlined,
  ProfileOutlined,
  BookOutlined,
  CheckCircleOutlined,
  CompassOutlined,
  ShopOutlined,
  SearchOutlined,
  ReadOutlined,
  BulbOutlined,
  LineChartOutlined,
  PlayCircleOutlined,
  FireOutlined,
  MinusOutlined,
} from '@ant-design/icons-vue'

// 后端 registry 内置头像 emoji → 语义图标
const EMOJI_ICON_MAP = {
  '🔬': ExperimentOutlined, // 材料发现
  '⚗️': ExperimentOutlined, // 合成规划
  '🧮': CalculatorOutlined, // 建模
  '📊': BarChartOutlined, // 分析简报
  '📋': ProfileOutlined, // 数据
  '📚': BookOutlined, // 文献
  '✅': CheckCircleOutlined, // 质量审核
  '🧭': CompassOutlined, // 路由/导航
  '🏭': ShopOutlined, // 工业化
  '🔍': SearchOutlined, // 检索
  '🎓': ReadOutlined, // 评估
  '🧠': BulbOutlined, // 推理
  '🔮': LineChartOutlined, // 预测
  '🤖': RobotOutlined, // 默认
  '💭': BulbOutlined,
  '▶': PlayCircleOutlined,
  '✔': CheckCircleOutlined,
  '🎉': FireOutlined,
  '·': MinusOutlined,
}

/**
 * 将 avatar 字段解析为图标组件。
 * @param {string} avatar 后端 avatar 字段（可能为 emoji 或空）
 * @returns 图标组件；非已知 emoji 视为普通文本时返回 null
 */
export function resolveAgentIcon(avatar) {
  if (!avatar) return RobotOutlined
  return EMOJI_ICON_MAP[avatar] || null
}

/** avatar 是否为已知 emoji（可安全替换为图标） */
export function isEmojiAvatar(avatar) {
  return Boolean(avatar && EMOJI_ICON_MAP[avatar])
}
