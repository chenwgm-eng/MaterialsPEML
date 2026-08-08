/**
 * 表单校验规则工厂（P1-FORM-001）
 *
 * 解决问题：所有创建/编辑表单缺少 :rules 前端校验
 *
 * 用法：
 *   import { required, lengthRange, numberRange, email, casNumber, url } from '@/utils/formRules'
 *   const rules = {
 *     name: required('请输入名称'),
 *     email: email(),
 *     purity: numberRange(0, 100, '纯度必须在 0-100 之间'),
 *   }
 */

/** 必填字段 */
export function required(message = '此项为必填', trigger = 'blur') {
  return [{ required: true, message, trigger }]
}

/** 必填选择字段（select/datepicker 用 change 触发） */
export function requiredSelect(message = '请选择', trigger = 'change') {
  return [{ required: true, message, trigger }]
}

/** 字符串长度范围 */
export function lengthRange(min, max, message = '', trigger = 'blur') {
  return [
    {
      min,
      max,
      message: message || `长度需在 ${min}-${max} 个字符之间`,
      trigger,
    },
  ]
}

/** 数值范围 */
export function numberRange(min, max, message = '', trigger = 'blur') {
  return [
    { type: 'number', message: '请输入有效数值', trigger },
    {
      validator: (_rule, value) => {
        if (value === null || value === undefined || value === '') return Promise.resolve()
        const num = Number(value)
        if (Number.isNaN(num)) return Promise.reject('请输入有效数值')
        if (num < min || num > max) {
          return Promise.reject(message || `数值需在 ${min}-${max} 之间`)
        }
        return Promise.resolve()
      },
      trigger,
    },
  ]
}

/** 非负数 */
export function nonNegative(message = '数值不能为负', trigger = 'blur') {
  return [
    { type: 'number', message: '请输入有效数值', trigger },
    {
      validator: (_rule, value) => {
        if (value === null || value === undefined || value === '') return Promise.resolve()
        const num = Number(value)
        if (Number.isNaN(num)) return Promise.reject('请输入有效数值')
        if (num < 0) return Promise.reject(message)
        return Promise.resolve()
      },
      trigger,
    },
  ]
}

/** 邮箱格式 */
export function email(message = '请输入有效的邮箱地址', trigger = 'blur') {
  return [{ type: 'email', message, trigger }]
}

/** URL 格式 */
export function url(message = '请输入有效的 URL', trigger = 'blur') {
  return [
    {
      validator: (_rule, value) => {
        if (!value) return Promise.resolve()
        try {
          new URL(value)
          return Promise.resolve()
        } catch {
          return Promise.reject(message)
        }
      },
      trigger,
    },
  ]
}

/** CAS 号格式（如 12136-58-2） */
export function casNumber(message = 'CAS 号格式不正确（如 12136-58-2）', trigger = 'blur') {
  return [
    {
      pattern: /^\d{1,7}-\d{2}-\d$/,
      message,
      trigger,
    },
  ]
}

/** 化学式非空校验（宽松，仅检查非空） */
export function chemicalFormula(message = '请输入化学式', trigger = 'blur') {
  return [{ required: false, message, trigger }]
}

/** 日期不晚于另一字段（getOtherValue 返回另一字段的当前值，闭包动态读取） */
export function dateNotAfter(getOtherValue, otherLabel = '结束日期', trigger = 'change') {
  return [
    {
      validator: (_rule, value) => {
        if (!value) return Promise.resolve()
        const other = getOtherValue?.()
        if (other && value > other) {
          return Promise.reject(new Error(`不得晚于${otherLabel}`))
        }
        return Promise.resolve()
      },
      trigger,
    },
  ]
}

/** 创建日期联动校验规则（需在组件中用 computed 动态引用） */
export function dateRangeRules(getStartDate, getEndDate) {
  return {
    start: [
      {
        validator: () => {
          const s = getStartDate()
          const e = getEndDate()
          if (s && e && s > e) return Promise.reject('开始日期不能晚于结束日期')
          return Promise.resolve()
        },
        trigger: 'change',
      },
    ],
    end: [
      {
        validator: () => {
          const s = getStartDate()
          const e = getEndDate()
          if (s && e && s > e) return Promise.reject('结束日期不能早于开始日期')
          return Promise.resolve()
        },
        trigger: 'change',
      },
    ],
  }
}

/** 组合多条规则 */
export function compose(...ruleArrays) {
  return ruleArrays.flat()
}
