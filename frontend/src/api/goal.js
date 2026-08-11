import client from './client'

// 智能目标框：一句话研发目标 → 结构化上下文（Q12）
export function parseGoal(goal) {
  return client.post('/parse-goal', { goal }).then((r) => r)
}
